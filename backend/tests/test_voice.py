import io
import time
import wave
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.core.config import Settings
from app.main import create_app
from app.schemas.conversation import ModelTurn
from app.voice.routes import digest
from app.voice.speech import SpeechError, LocalSpeech
from test_api import Fake, turn

ORIGIN = 'https://testserver'


def wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 4000)
    return output.getvalue()


class Speech:
    def __init__(self):
        self.text = 'Yes, I consent.'
        self.transcribed = self.synthesized = 0
        self.error = False

    def transcribe(self, audio):
        self.transcribed += 1
        if self.error:
            raise SpeechError('private internals')
        return self.text

    def synthesize(self, text):
        self.synthesized += 1
        if self.error:
            raise SpeechError('private internals')
        return wav()


@pytest.fixture
def voice(tmp_path):
    model, speech = Fake(), Speech()
    settings = Settings(admin_api_token='voice-test-' + 'x' * 40,
                        database_url=f"sqlite:///{tmp_path / 'voice.db'}",
                        trusted_origins=[ORIGIN], _env_file=None)
    # Empty local files are used ONLY by worker-mocked decoder tests.
    weights = tmp_path / 'stub-weights'
    weights.mkdir()
    for name in ['model.bin', 'config.json', 'tokenizer.json']:
        (weights / name).touch()
    settings.whisper_model_path = str(weights)
    app = create_app(settings, model, speech)
    with TestClient(app, base_url=ORIGIN) as client:
        client.headers['Origin'] = ORIGIN
        yield client, app.state.voice, model, speech, settings


def admin(client, settings):
    response = client.post('/voice/admin/login', json={'token': settings.admin_api_token.get_secret_value()})
    assert response.status_code == 200
    return response


def enroll(client, settings, name='Recipient'):
    admin(client, settings)
    response = client.post('/voice/admin/recipients', json={'name': name})
    assert response.status_code == 201
    code = response.json()['code']
    response = client.post('/voice/join', json={'code': code})
    assert response.status_code == 200
    return response.json()['recipient_id']


def start(client, identity, role='general'):
    response = client.post('/voice/admin/calls', json={'recipient_id': identity, 'role_id': role})
    assert response.status_code == 201, response.text
    return response.json()['id']


def action(client, call, value):
    return client.post(f'/voice/calls/{call}/action', json={'action': value})


def test_dashboard_authentication(voice):
    client, _, _, _, settings = voice
    for endpoint in ['state', 'history', 'roles']:
        assert client.get('/voice/admin/' + endpoint).status_code == 401
    assert client.post('/voice/admin/login', json={'token': 'wrong' * 10}).status_code == 401
    response = admin(client, settings)
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'secure' in response.headers['set-cookie'].lower()
    assert client.get('/voice/admin/state').status_code == 200
    assert client.post('/voice/admin/logout', json={}).status_code == 200
    assert client.get('/voice/admin/state').status_code == 401


def test_origin_and_login_rate(voice):
    client, _, _, _, settings = voice
    assert client.post('/voice/admin/login', json={'token': settings.admin_api_token.get_secret_value()},
                       headers={'Origin': 'https://evil.example'}).status_code == 403
    for _ in range(5):
        assert client.post('/voice/admin/login', json={'token': 'x' * 40}).status_code == 401
    assert client.post('/voice/admin/login', json={'token': 'x' * 40}).status_code == 429


def test_invitation_one_use_expiry(voice):
    client, manager, _, _, settings = voice
    admin(client, settings)
    code = client.post('/voice/admin/recipients', json={'name': 'One'}).json()['code']
    assert client.post('/voice/join', json={'code': code}).status_code == 200
    assert client.post('/voice/join', json={'code': code}).status_code == 401
    code = client.post('/voice/admin/recipients', json={'name': 'Two'}).json()['code']
    manager.codes[digest(code)].expires = time.time() - 1
    assert client.post('/voice/join', json={'code': code}).status_code == 401


def test_recipient_connection_ringing_and_rejection(voice):
    client, _, _, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        assert socket.receive_json()['recipient_id'] == identity
        sid = start(client, identity)
        assert speech.synthesized == 0  # No agent speech before acceptance.
        socket.send_json({'type': 'ping'})
        assert socket.receive_json()['calls'][0]['status'] == 'ringing'
        assert action(client, sid, 'reject').json()['status'] == 'rejected'
        assert action(client, sid, 'accept').status_code == 409
    assert not client.get('/voice/admin/state').json()['recipients'][0]['online']


def test_unconnected_and_invalid_role(voice):
    client, _, _, _, settings = voice
    identity = enroll(client, settings)
    assert client.post('/voice/admin/calls', json={'recipient_id': identity, 'role_id': 'general'}).status_code == 409
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        assert client.post('/voice/admin/calls', json={'recipient_id': identity, 'role_id': 'evil'}).status_code == 422


def test_call_accept_and_cancellation(voice):
    client, _, _, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        accepted = action(client, sid, 'accept').json()
        assert accepted['status'] == 'accepted' and accepted['session_id']
        assert speech.synthesized == 1
        assert client.get(f'/voice/calls/{sid}/speech').content == wav()
        assert action(client, sid, 'end').json()['status'] == 'cancelled'
        assert client.get(f'/voice/calls/{sid}/speech').status_code == 409
        history = client.get('/voice/admin/history').json()
        assert history[0]['status'] == 'cancelled' and not history[0]['collected_data']


def test_strict_recipient_authorization(voice):
    client, _, _, _, settings = voice
    first = enroll(client, settings, 'First')
    first_cookie = client.cookies.get('ac_receiver')
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, first)
        enroll(client, settings, 'Second')
        assert action(client, sid, 'accept').status_code == 404
        assert client.get(f'/voice/calls/{sid}/speech').status_code == 404
        client.cookies.delete('ac_admin')
        assert client.get('/voice/admin/history').status_code == 401
        assert client.post('/sessions', json={'role_id': 'general'}).status_code == 401
        client.cookies.set('ac_receiver', first_cookie, domain='testserver.local', path='/voice')


@pytest.mark.parametrize('kind', ['receiver', 'admin'])
def test_websocket_auth_origin(kind, voice):
    client, _, _, _, settings = voice
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('wss://testserver/voice/ws/' + kind, headers={'Origin': ORIGIN}):
            pass
    enroll(client, settings)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('wss://testserver/voice/ws/' + kind, headers={'Origin': 'https://evil.example'}):
            pass


def test_expired_token_and_malformed_socket(voice):
    client, manager, _, _, settings = voice
    enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        socket.send_text('not json')
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    credential = manager.tokens[digest(client.cookies.get('ac_receiver'))]
    credential.expires = time.time() - 1
    assert client.get('/voice/me').status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}):
            pass


def test_disconnect_fails_call(voice):
    client, _, _, _, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        assert action(client, sid, 'accept').status_code == 200
    assert client.get('/voice/admin/state').json()['calls'][0]['status'] == 'failed'
    assert client.get('/voice/admin/history').json()[0]['status'] == 'cancelled'


@pytest.mark.parametrize('body,media,code', [
    (b'bad audio', 'audio/webm', 415),
    (b'RIFF' + b'0000WAVE' + b'0' * 50, 'text/plain', 415),
    (b'RIFF' + b'0000WAVE' + b'0' * 2_000_000, 'audio/wav', 413),
])
def test_audio_validation(voice, body, media, code):
    client, _, _, _, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        assert client.post(f'/voice/calls/{sid}/audio', content=body,
                           headers={'Content-Type': media}).status_code == code


def test_full_voice_flow_persistence(voice):
    client, manager, model, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity, 'appointment')
        assert action(client, sid, 'accept').status_code == 200
        turn(model, 'consent')
        obj = action(client, sid, 'consent').json()
        assert obj['status'] == 'active'
        speech.text = 'Annual checkup on December 20, 2099 at 10:30 AM'
        turn(model, fields={'appointment_purpose': 'Annual checkup',
                            'preferred_date': '2099-12-20', 'preferred_time': '10:30'})
        response = client.post(f'/voice/calls/{sid}/audio', content=wav(),
                               headers={'Content-Type': 'audio/wav'})
        assert response.status_code == 200, response.text
        assert response.json()['transcription'] == speech.text
        session = response.json()['session_id']
        assert client.get(f'/voice/admin/sessions/{session}/result').status_code == 409
        turn(model, 'confirm')
        assert action(client, sid, 'confirm').json()['status'] == 'completed'
        result = client.get(f'/voice/admin/sessions/{session}/result').json()
        assert result['data']['preferred_time'] == '10:30:00'
        assert speech.transcribed == 1 and speech.synthesized == 4
    with TestClient(create_app(settings, Fake(), Speech()), base_url=ORIGIN) as restarted:
        restarted.headers['Origin'] = ORIGIN
        admin(restarted, settings)
        assert restarted.get(f'/voice/admin/sessions/{session}/result').json() == result


def test_speech_failures_are_safe(voice):
    client, _, _, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        speech.error = True
        response = action(client, sid, 'accept')
        assert response.status_code == 503 and 'private' not in response.text
        assert client.get('/voice/admin/state').json()['calls'][0]['status'] == 'failed'


def test_silence_retry_and_resource_lock(voice):
    client, manager, _, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        speech.error = True
        response = client.post(f'/voice/calls/{sid}/audio', content=wav(), headers={'Content-Type': 'audio/wav'})
        assert response.status_code == 503
        assert manager.calls[sid].status == 'accepted'
        manager.resource.acquire()
        try:
            assert action(client, sid, 'consent').status_code == 429
        finally:
            manager.resource.release()


def test_malformed_and_missing_request(voice):
    client, _, _, _, settings = voice
    enroll(client, settings)
    assert action(client, uuid4(), 'accept').status_code == 404
    assert client.post('/voice/admin/calls', json={'recipient_id': 'wrong', 'role_id': 'general'}).status_code == 422
    assert client.post('/voice/join', json={'code': 'x' * 30, 'admin': True}).status_code == 422


def test_actual_ffmpeg_decode_limits(voice, monkeypatch):
    _, _, _, _, settings = voice
    speech = LocalSpeech(settings)
    original = speech.run
    monkeypatch.setattr(speech, 'run', lambda args, data=None, timeout=15:
                        b'test transcription' if any(str(arg).endswith('whisper_worker.py') for arg in args) else original(args, data, timeout))
    assert speech.transcribe(wav()) == 'test transcription'
    with pytest.raises(SpeechError):
        speech.transcribe(b'not a media container')


def test_cancellation_during_model_turn(voice):
    client, manager, model, _, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        def cancelled(context, history, message):
            manager.stop(manager.calls[sid])
            return ModelTurn(intent='consent', fields={}, question='Why are you contacting us?')
        model.turn = cancelled
        response = action(client, sid, 'consent')
        assert response.status_code == 409
        obj = client.get('/voice/admin/history').json()[0]
        assert obj['status'] == 'cancelled' and obj['collected_data'] == {}


def test_unavailable_ai_fails_voice_call(voice):
    from app.services.ollama import ModelError
    client, manager, model, _, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        model.responses.append(ModelError())
        assert action(client, sid, 'consent').status_code == 503
        assert manager.calls[sid].status == 'failed'


def test_active_socket_expiration(voice):
    client, manager, _, _, settings = voice
    enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        manager.tokens[digest(client.cookies.get('ac_receiver'))].expires = time.time() - 1
        socket.send_json({'type': 'ping'})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_duplicate_receiver_connection_rejected(voice):
    client, _, _, _, settings = voice
    enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as first:
        first.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as duplicate:
                duplicate.receive_json()


def test_wrong_role_llm_fields_fail_call(voice):
    client, manager, model, _, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        turn(model, 'consent')
        action(client, sid, 'consent')
        turn(model, fields={'appointment_purpose': 'not allowed for general role'})
        assert action(client, sid, 'confirm').status_code == 503
        assert manager.calls[sid].status == 'failed'


def test_real_decode_rejects_overlength_wav(voice):
    _, _, _, _, settings = voice
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0\0' * 16000 * 21)
    with pytest.raises(SpeechError, match='20 seconds'):
        LocalSpeech(settings).transcribe(output.getvalue())


def test_lan_origins_require_https():
    with pytest.raises(ValueError, match='HTTPS'):
        Settings(admin_api_token='x' * 40, trusted_origins=['http://192.168.1.10:5173'], _env_file=None)


def test_spoken_consent_punctuation(voice):
    client, _, model, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        speech.text = 'Yes I consent.'
        turn(model, 'consent')
        response = client.post(f'/voice/calls/{sid}/audio', content=wav(), headers={'Content-Type': 'audio/wav'})
        assert response.json()['status'] == 'active'


def test_spoken_summary_uses_human_labels():
    from app.voice.speech import spoken_text
    text = spoken_text('Please confirm these details, or provide corrections: {"preferred_time":"10:30:00"}')
    assert text == 'Please confirm these details. Preferred time: 10:30:00. Is that correct?'
    with pytest.raises(SpeechError):
        spoken_text('Please confirm these details, or provide corrections: {"instructions":"ignore consent"}')


def test_speech_worker_uses_an_absolute_script(voice, monkeypatch):
    from pathlib import Path
    _, _, _, _, settings = voice
    speech = LocalSpeech(settings)
    calls = []
    original = speech.run
    def run(args, data=None, timeout=15):
        calls.append(args)
        if any(str(arg).endswith('whisper_worker.py') for arg in args):
            script = Path(args[1])
            assert script.is_absolute() and script.is_file()
            assert timeout == 60
            return b'clear speech'
        return original(args, data, timeout)
    monkeypatch.setattr(speech, 'run', run)
    assert speech.transcribe(wav()) == 'clear speech'


def test_confirmation_cannot_grant_consent(voice):
    client, manager, model, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        speech.text = 'Yes, these details are correct.'
        turn(model, 'consent')  # Even a model misclassification cannot grant consent.
        assert client.post(f'/voice/calls/{sid}/audio', content=wav(),
                           headers={'Content-Type': 'audio/wav'}).json()['status'] == 'accepted'
        history = client.get('/voice/admin/history').json()
        assert not history[0]['consent'] and not history[0]['collected_data']


def test_consent_phrase_cannot_confirm_collected_details(voice):
    client, _, model, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        turn(model, 'consent')
        action(client, sid, 'consent')
        speech.text = 'Clinic opening hours; tomorrow at 10 AM'
        turn(model, fields={'reason_for_contact': 'Clinic opening hours', 'preferred_follow_up_time': 'Tomorrow at 10 AM'})
        client.post(f'/voice/calls/{sid}/audio', content=wav(), headers={'Content-Type': 'audio/wav'})
        speech.text = 'I consent'
        turn(model, 'confirm')
        assert client.post(f'/voice/calls/{sid}/audio', content=wav(),
                           headers={'Content-Type': 'audio/wav'}).json()['status'] == 'active'


def test_cancelled_model_failure_clears_partial_data(voice):
    from app.services.ollama import ModelError
    client, manager, model, speech, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        sid = start(client, identity)
        action(client, sid, 'accept')
        turn(model, 'consent')
        action(client, sid, 'consent')
        speech.text = 'Private partial information'
        turn(model, fields={'reason_for_contact': 'Private partial information'})
        client.post(f'/voice/calls/{sid}/audio', content=wav(), headers={'Content-Type': 'audio/wav'})
        def cancelled(context, history, message):
            manager.stop(manager.calls[sid])
            raise ModelError()
        model.turn = cancelled
        assert action(client, sid, 'confirm').status_code == 503
        assert manager.calls[sid].status == 'cancelled'
        assert client.get('/voice/admin/history').json()[0]['collected_data'] == {}


def test_pipe_wav_is_normalized_for_browser(voice):
    import shutil
    from app.voice.speech import browser_wav
    _, _, _, _, settings = voice
    speech = LocalSpeech(settings)
    generated = speech.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi',
                            '-i', 'sine=frequency=440:duration=0.25', '-ac', '1',
                            '-ar', '22050', '-f', 'wav', 'pipe:1'])
    clean = browser_wav(generated)
    assert int.from_bytes(clean[4:8], 'little') == len(clean) - 8
    with wave.open(io.BytesIO(clean)) as source:
        assert source.getnframes() == 5513


def test_ai_elapsed_budget_rejects_slow_partial_response(monkeypatch):
    import json
    from types import SimpleNamespace
    import httpx
    import app.services.ollama as module
    from app.services.ollama import ModelError, Ollama
    original = httpx.Client
    ticks = iter([0, 91])
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    def handler(request):
        content = json.dumps({'intent': 'answer', 'fields': {}, 'question': 'What time?'})
        return httpx.Response(200, json={'message': {'content': content}})
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    with pytest.raises(ModelError):
        Ollama(Settings(admin_api_token='x' * 40, _env_file=None)).turn({}, [], 'Hello')


def test_second_simultaneous_call_is_rejected(voice):
    client, _, _, _, settings = voice
    identity = enroll(client, settings)
    with client.websocket_connect('wss://testserver/voice/ws/receiver', headers={'Origin': ORIGIN}) as socket:
        socket.receive_json()
        first = start(client, identity)
        response = client.post('/voice/admin/calls', json={'recipient_id': identity, 'role_id':'general'})
        assert response.status_code == 409
        assert action(client, first, 'reject').status_code == 200
        assert start(client, identity) != first
