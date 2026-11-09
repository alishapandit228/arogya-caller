"""Browser-test-only adapters. Never used by the normal app factory."""
import io
import wave
from app.core.config import Settings
from app.main import create_app
from app.schemas.conversation import ModelTurn
from app.voice.speech import LocalSpeech


class Model:
    def turn(self, context, history, message):
        if context['status'] == 'awaiting_consent':
            return ModelTurn(intent='consent', fields={}, question='What is your reason for contact?')
        if context['confirmation_pending']:
            return ModelTurn(intent='confirm', fields={}, question='Thank you.')
        return ModelTurn(intent='answer', fields={
            'reason_for_contact': 'Clinic opening hours',
            'preferred_follow_up_time': 'Tomorrow at 10 AM',
        }, question='Are these details correct?')


class Speech:
    def transcribe(self, data):
        LocalSpeech(Settings()).decode(data)  # Real browser-codec/FFmpeg integration.
        return 'Clinic opening hours; tomorrow at 10 AM'

    def synthesize(self, text):
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 4000)
        return output.getvalue()


def create():
    return create_app(Settings(), Model(), Speech())
