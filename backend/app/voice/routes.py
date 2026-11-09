"""Same-origin HTTP actions and cookie-authenticated WebSocket signaling."""
import asyncio
import json
import secrets
import time
from uuid import UUID, uuid4
import anyio
from fastapi import HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from app.agents.roles import ROLES
from app.schemas.conversation import CreateSession
from app.voice.manager import Voice, Credential, Recipient, Call, digest, TERMINAL
from app.voice.speech import SpeechError


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Input):
    token: str = Field(min_length=32, max_length=256)


class Enroll(Input):
    name: str = Field(min_length=1, max_length=60)


class Join(Input):
    code: str = Field(min_length=20, max_length=128)


class StartCall(Input):
    recipient_id: UUID
    role_id: str = Field(min_length=1, max_length=50)


class Action(Input):
    action: str = Field(pattern='^(accept|reject|end|consent|confirm|refuse)$')



def mount_voice(app, settings, factory, create, reply, cancel, listing, get, result, roles, speech):
    voice = Voice(settings, factory, create, reply, cancel, speech)
    app.state.voice = voice

    def mutating(request):
        voice.origin(request.headers.get('origin'))

    def cookie(response, name, value):
        response.set_cookie(name, value, max_age=3600, httponly=True,
                            secure=settings.voice_cookie_secure, samesite='strict', path='/voice')

    @app.post('/voice/admin/login')
    def login(payload: Login, request: Request, response: Response):
        mutating(request)
        voice.limited('login:' + (request.client.host if request.client else 'local'), 5)
        if not secrets.compare_digest(payload.token.encode(), settings.admin_api_token.get_secret_value().encode()):
            raise HTTPException(401, 'Invalid authentication')
        token = secrets.token_urlsafe(48)
        with voice.lock:
            voice.admins = {k: v for k, v in voice.admins.items() if v.expires > time.time()}
            if len(voice.admins) >= 16:
                raise HTTPException(429, 'Too many administrator sessions')
            voice.admins[digest(token)] = Credential('admin', time.time() + 3600)
        cookie(response, 'ac_admin', token)
        return {'authenticated': True, 'expires_in': 3600}

    @app.post('/voice/admin/logout')
    def logout(request: Request, response: Response):
        mutating(request)
        with voice.lock:
            voice.admins.pop(digest(request.cookies.get('ac_admin', '')), None)
        response.delete_cookie('ac_admin', path='/voice', secure=settings.voice_cookie_secure,
                               httponly=True, samesite='strict')
        return {'authenticated': False}

    @app.get('/voice/admin/state')
    def state(request: Request):
        voice.admin(request)
        return voice.snapshot()

    @app.get('/voice/admin/roles')
    def role_list(request: Request):
        voice.admin(request)
        return roles()

    @app.get('/voice/admin/history')
    def history(request: Request):
        voice.admin(request)
        with factory() as db:
            return listing(limit=100, offset=0, session=db)

    @app.get('/voice/admin/sessions/{session_id}/result')
    def results(session_id: UUID, request: Request):
        voice.admin(request)
        with factory() as db:
            return result(session_id, session=db)

    @app.post('/voice/admin/recipients', status_code=201)
    def enroll(payload: Enroll, request: Request):
        mutating(request)
        voice.admin(request)
        voice.limited('enrollment', 20)
        with voice.lock:
            voice.codes = {k: v for k, v in voice.codes.items() if v.expires > time.time()}
            if len(voice.recipients) + len(voice.codes) >= 50:
                raise HTTPException(429, 'Recipient limit reached; restart to clear enrollments')
            identity, code = str(uuid4()), secrets.token_urlsafe(32)
            voice.codes[digest(code)] = Credential(json.dumps([identity, payload.name]), time.time() + 300)
        return {'recipient_id': identity, 'code': code, 'expires_in': 300}

    @app.post('/voice/join')
    def join(payload: Join, request: Request, response: Response):
        mutating(request)
        voice.limited('join:' + (request.client.host if request.client else 'local'), 10)
        with voice.lock:
            record = voice.codes.pop(digest(payload.code), None)
            if not record or record.expires <= time.time():
                raise HTTPException(401, 'Invitation expired or invalid')
            identity, name = json.loads(record.identity)
            voice.recipients[identity] = Recipient(identity, name)
            token = secrets.token_urlsafe(48)
            voice.tokens[digest(token)] = Credential(identity, time.time() + 3600)
        cookie(response, 'ac_receiver', token)
        return {'recipient_id': identity, 'name': name, 'expires_in': 3600}

    @app.get('/voice/me')
    def me(request: Request):
        identity = voice.recipient(request)
        return {**voice.snapshot(identity), 'name': voice.recipients[identity].name}

    @app.post('/voice/admin/calls', status_code=201)
    def initiate(payload: StartCall, request: Request):
        mutating(request)
        voice.admin(request)
        voice.limited('call-initiation', 20)
        with voice.lock:
            recipient = voice.recipients.get(str(payload.recipient_id))
            if not recipient or not recipient.online:
                raise HTTPException(409, 'Recipient is not connected')
            if payload.role_id not in ROLES:
                raise HTTPException(422, 'Unknown role')
            if any(c.status not in TERMINAL for c in voice.calls.values()):
                raise HTTPException(409, 'One call at a time on this prototype')
            voice.calls = {k: c for k, c in voice.calls.items() if c.status not in TERMINAL}
            call = Call(str(uuid4()), recipient.id, payload.role_id)
            voice.calls[call.id] = call
            voice.save(call)
            return voice.view(call)

    @app.post('/voice/admin/calls/{call_id}/end')
    def admin_end(call_id: UUID, request: Request):
        mutating(request)
        voice.admin(request)
        return voice.stop(voice.owned(call_id))

    @app.post('/voice/calls/{call_id}/action')
    def action(call_id: UUID, payload: Action, request: Request):
        mutating(request)
        identity = voice.recipient(request)
        voice.limited(identity)
        call = voice.owned(call_id, identity)
        if payload.action in {'end', 'refuse'}:
            return voice.stop(call)
        if payload.action == 'reject':
            with voice.lock:
                if call.status != 'ringing':
                    raise HTTPException(409, 'Call is not ringing')
                return voice.stop(call, 'rejected')
        if payload.action == 'accept':
            def accept():
                with voice.lock:
                    if call.status != 'ringing':
                        raise HTTPException(409, 'Call is not ringing')
                    with factory() as db:
                        created = create(CreateSession(role_id=call.role_id), session=db)
                    call.status, call.session_id = 'accepted', created['id']
                    voice.save(call)
                try:
                    voice.speak(call, created['message'])
                except SpeechError:
                    voice.stop(call, 'failed')
                    raise
                return voice.view(call)
            return voice.work(accept)
        message = 'Yes, I consent.' if payload.action == 'consent' else 'Yes, these details are correct.'
        return voice.work(lambda: voice.turn(call, message))

    @app.post('/voice/calls/{call_id}/audio')
    async def upload(call_id: UUID, request: Request):
        mutating(request)
        identity = voice.recipient(request)
        voice.limited(identity)
        call = voice.owned(call_id, identity)
        body = await request.body()
        media = request.headers.get('content-type', '').split(';')[0]
        valid_header = (body.startswith(b'RIFF') and body[8:12] == b'WAVE' or
                        body.startswith(b'\x1a\x45\xdf\xa3') or body[4:8] == b'ftyp')
        if media not in {'audio/webm', 'audio/mp4', 'audio/wav'} or not valid_header:
            raise HTTPException(415, 'Expected browser WebM/MP4 or WAV audio')
        if not 44 <= len(body) <= 2_000_000:
            raise HTTPException(413, 'Audio must be at most 2 MB')
        def process():
            if call.status not in {'accepted', 'active'}:
                raise HTTPException(409, 'Call is not active')
            text = voice.speech.transcribe(body)
            return voice.turn(call, text)
        return await anyio.to_thread.run_sync(lambda: voice.work(process))

    @app.get('/voice/calls/{call_id}/speech')
    def audio(call_id: UUID, request: Request):
        identity = voice.recipient(request)
        call = voice.owned(call_id, identity)
        if not call.audio or call.status in {'ringing', 'cancelled', 'rejected', 'failed'}:
            raise HTTPException(409, 'No speech is ready')
        return Response(call.audio, media_type='audio/wav', headers={'Cache-Control': 'no-store'})

    @app.websocket('/voice/ws/{kind}')
    async def websocket(ws: WebSocket, kind: str):
        identity, connected = None, False
        try:
            voice.origin(ws.headers.get('origin'))
            if kind not in {'admin', 'receiver'}:
                await ws.close(4404)
                return
            name = 'ac_admin' if kind == 'admin' else 'ac_receiver'
            credential = voice.credential(ws.cookies.get(name), kind == 'admin')
            if kind == 'receiver':
                identity = credential.identity
                with voice.lock:
                    recipient = voice.recipients[identity]
                    duplicate = recipient.socket is not None
                    if not duplicate:
                        recipient.online, recipient.socket = True, ws
                        connected = True
                if duplicate:
                    await ws.accept()
                    await ws.close(4409)
                    return
            await ws.accept()
            while True:
                voice.credential(ws.cookies.get(name), kind == 'admin')
                snapshot = await anyio.to_thread.run_sync(lambda: voice.snapshot(identity))
                await ws.send_json(snapshot)
                try:
                    message = await asyncio.wait_for(ws.receive_text(), timeout=1)
                    voice.limited('ws:' + (identity or 'admin'), 120)
                    if len(message) > 128 or json.loads(message) != {'type': 'ping'}:
                        await ws.close(1008)
                        return
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        except (HTTPException, ValueError, KeyError):
            await ws.close(4401)
        finally:
            if connected:
                with voice.lock:
                    recipient = voice.recipients.get(identity)
                    if recipient and recipient.socket is ws:
                        recipient.online, recipient.socket = False, None
                    calls = [c for c in voice.calls.values() if c.recipient_id == identity and
                             c.status not in TERMINAL]
                for call in calls:
                    await anyio.to_thread.run_sync(lambda c=call: voice.stop(c, 'failed'))
