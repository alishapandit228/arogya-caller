"""Bounded in-memory credentials and durable call/session coordination."""
from dataclasses import dataclass, field
import hashlib
import threading
import time
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from app.agents.roles import ROLES
from app.models.session import Conversation
from app.schemas.conversation import Reply
from app.voice.models import CallRecord
from app.voice.speech import LocalSpeech, SpeechError

TERMINAL = {'completed', 'cancelled', 'rejected', 'failed'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class Credential:
    identity: str
    expires: float


@dataclass
class Recipient:
    id: str
    name: str
    online: bool = False
    socket: object = None


@dataclass
class Call:
    id: str
    recipient_id: str
    role_id: str
    status: str = 'ringing'
    session_id: str | None = None
    message: str = ''
    audio: bytes = b''
    created: float = field(default_factory=time.time)
    last_turn: float = field(default_factory=time.time)


class Voice:
    def __init__(self, settings, factory, create, reply, cancel, speech):
        self.settings, self.factory = settings, factory
        self.create, self.reply, self.cancel = create, reply, cancel
        self.speech = speech or LocalSpeech(settings)
        self.lock, self.resource = threading.RLock(), threading.Lock()
        self.admins, self.tokens, self.codes = {}, {}, {}
        self.recipients, self.calls, self.rates = {}, {}, {}

    def limited(self, key, limit=60):
        with self.lock:
            now = time.time()
            self.rates = {k: v for k, v in self.rates.items() if v[1] > now}
            count, expiry = self.rates.get(key, (0, now + 60))
            if count >= limit or len(self.rates) >= 256:
                raise HTTPException(429, 'Rate limit reached')
            self.rates[key] = (count + 1, expiry)

    def origin(self, value):
        if not value or value not in self.settings.trusted_origins:
            raise HTTPException(403, 'Untrusted origin')

    def credential(self, value, admin=False):
        with self.lock:
            item = (self.admins if admin else self.tokens).get(digest(value or ''))
            if item is None or item.expires <= time.time():
                raise HTTPException(401, 'Authentication expired or invalid')
            return item

    def admin(self, request):
        return self.credential(request.cookies.get('ac_admin'), True)

    def recipient(self, request):
        return self.credential(request.cookies.get('ac_receiver')).identity

    def save(self, call):
        with self.factory() as db:
            record = db.get(CallRecord, call.id)
            if record is None:
                record = CallRecord(id=call.id, recipient_id=call.recipient_id,
                                    role_id=call.role_id, status=call.status)
                db.add(record)
            record.status, record.session_id = call.status, call.session_id
            db.commit()

    def owned(self, call_id, recipient=None):
        call = self.calls.get(str(call_id))
        if call is None or recipient is not None and call.recipient_id != recipient:
            raise HTTPException(404, 'Call not found')
        return call

    def view(self, call):
        return {'id': call.id, 'recipient_id': call.recipient_id, 'role_id': call.role_id,
                'status': call.status, 'session_id': call.session_id, 'message': call.message,
                'role_name': ROLES[call.role_id].name}

    def stop(self, call, status='cancelled'):
        with self.lock:
            if call.status in TERMINAL:
                return self.view(call)
            call.status, call.audio, call.message = status, b'', 'The call has ended.'
            self.save(call)
        self.cleanup_session(call)
        return self.view(call)

    def cleanup_session(self, call):
        if call.session_id:
            try:
                with self.factory() as db:
                    self.cancel(UUID(call.session_id), session=db)
            except HTTPException as exc:
                if exc.status_code not in {409, 429}:
                    raise
                if exc.status_code == 409 and call.status in {'cancelled', 'failed'}:
                    with self.factory() as db:
                        item = db.get(Conversation, call.session_id)
                        # Privacy cleanup never changes a terminal state or confirmed result.
                        if item and item.status == 'failed':
                            item.data, item.consent, item.confirming = {}, False, False
                            item.missing = list(ROLES[item.role_id].required_fields)
                            db.commit()

    def recover(self):
        with self.factory() as db:
            for call in db.scalars(select(CallRecord).where(CallRecord.status.in_(
                    ['ringing', 'accepted', 'active']))):
                call.status = 'failed'
                if call.session_id:
                    session = db.get(Conversation, call.session_id)
                    if session and session.status in {'active', 'awaiting_consent'}:
                        session.status, session.data, session.consent = 'failed', {}, False
            db.commit()

    def snapshot(self, identity=None):
        with self.lock:
            now = time.time()
            stale = [c for c in self.calls.values() if c.status not in TERMINAL and (
                c.status == 'ringing' and now - c.created > 60 or now - c.last_turn > 900)]
        for call in stale:
            self.stop(call, 'failed')
        with self.lock:
            if identity:
                return {'type': 'state', 'recipient_id': identity, 'calls': [
                    self.view(c) for c in self.calls.values() if c.recipient_id == identity][-10:]}
            return {'type': 'state', 'recipients': [
                {'id': r.id, 'name': r.name, 'online': r.online}
                for r in self.recipients.values()], 'calls': [
                    self.view(c) for c in self.calls.values()][-50:]}

    def speak(self, call, text):
        audio = self.speech.synthesize(text)
        with self.lock:
            if call.status in {'cancelled', 'rejected', 'failed'}:
                raise HTTPException(409, 'Call ended during speech processing')
            call.message, call.audio = text, audio

    def turn(self, call, text):
        with self.lock:
            if call.status not in {'accepted', 'active'}:
                raise HTTPException(409, 'Call is not active')

        def commit(db, session):
            with self.lock:
                if call.status in TERMINAL:
                    db.rollback()
                    raise HTTPException(409, 'Call ended during AI processing')
                next_status = 'completed' if session.status == 'completed' else (
                    'cancelled' if session.status == 'cancelled' else (
                        'active' if session.status == 'active' else 'accepted'))
                db.get(CallRecord, call.id).status = next_status
                db.commit()
                call.status = next_status
        try:
            with self.factory() as db:
                result = self.reply(UUID(call.session_id), Reply(message=text), db, commit_hook=commit)
            if call.status == 'cancelled':
                call.audio, call.message = b'', result['message']
            else:
                self.speak(call, result['message'])
            call.last_turn = time.time()
            return {**self.view(call), 'transcription': text}
        except HTTPException as exc:
            if exc.status_code == 503:
                self.stop(call, 'failed')
            if call.status in TERMINAL:
                self.cleanup_session(call)
            raise
        except SpeechError:
            if call.status != 'completed':
                self.stop(call, 'failed')
            raise HTTPException(503, 'Offline speech processing failed') from None

    def work(self, operation):
        if not self.resource.acquire(blocking=False):
            raise HTTPException(429, 'Voice processor busy; retry after the current turn')
        try:
            return operation()
        except SpeechError:
            raise HTTPException(503, 'Offline speech processing failed; check local models') from None
        finally:
            self.resource.release()
