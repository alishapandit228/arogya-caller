"""Opt-in REAL offline speech and voice API checks; no mocks."""
import os
import secrets
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from app.voice.speech import LocalSpeech

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv('RUN_VOICE_INTEGRATION') != '1',
                       reason='Requires local Whisper weights, TTS, FFmpeg, and Ollama'),
]
ORIGIN = 'https://testserver'


def config(tmp_path):
    return Settings(admin_api_token=secrets.token_urlsafe(48),
                    database_url=f"sqlite:///{tmp_path / 'voice-real.db'}",
                    trusted_origins=[ORIGIN], _env_file=None)


def test_real_offline_speech_roundtrip(tmp_path):
    speech = LocalSpeech(config(tmp_path))
    wav = speech.synthesize('Yes, I consent.')
    assert wav.startswith(b'RIFF')
    transcript = speech.transcribe(wav)
    assert 'consent' in transcript.lower(), transcript


def test_real_voice_api_and_persistence(tmp_path):
    settings = config(tmp_path)
    speech = LocalSpeech(settings)
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        client.headers['Origin'] = ORIGIN
        assert client.post('/voice/admin/login', json={
            'token': settings.admin_api_token.get_secret_value()}).status_code == 200
        invite = client.post('/voice/admin/recipients', json={'name': 'Synthetic local test'}).json()
        person = client.post('/voice/join', json={'code': invite['code']}).json()
        with client.websocket_connect('wss://testserver/voice/ws/receiver',
                                      headers={'Origin': ORIGIN}) as socket:
            socket.receive_json()
            response = client.post('/voice/admin/calls', json={
                'recipient_id': person['recipient_id'], 'role_id': 'general'})
            assert response.status_code == 201, response.text
            call_id = response.json()['id']
            response = client.post(f'/voice/calls/{call_id}/action', json={'action': 'accept'})
            assert response.status_code == 200, response.text
            assert client.get(f'/voice/calls/{call_id}/speech').content.startswith(b'RIFF')
            messages = ['Yes, I consent.',
                        'I need information about clinic opening hours.',
                        'Please follow up tomorrow at ten AM.',
                        'Yes, these details are correct.']
            for index, text in enumerate(messages):
                wav = speech.synthesize(text)
                response = client.post(f'/voice/calls/{call_id}/audio', content=wav,
                                       headers={'Content-Type': 'audio/wav'})
                assert response.status_code == 200, response.text
                obj = response.json()
                if index == 0:
                    assert obj['status'] == 'active'
                if index == 2:
                    assert obj['message'].startswith('Please confirm')
            assert obj['status'] == 'completed', obj
            session_id = obj['session_id']
            result = client.get(f'/voice/admin/sessions/{session_id}/result')
            assert result.status_code == 200
            saved = result.json()
            assert 'clinic' in saved['data']['reason_for_contact'].lower()
            assert 'preferred_follow_up_time' in saved['data']
    with TestClient(create_app(settings), base_url=ORIGIN) as restarted:
        restarted.headers['Origin'] = ORIGIN
        restarted.post('/voice/admin/login', json={'token': settings.admin_api_token.get_secret_value()})
        assert restarted.get(f'/voice/admin/sessions/{session_id}/result').json() == saved
