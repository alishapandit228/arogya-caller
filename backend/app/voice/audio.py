"""Shared bounded WAV and spoken-summary validation."""
import io
import json
import wave

class SpeechError(Exception):
    public_message = None


class SpeechSetupError(SpeechError):
    MESSAGES = {
        "whisper": "Local Whisper weights are missing. Install WHISPER_MODEL_PATH before calling.",
        "piper_model": "Local Piper voice/config are missing. Download PIPER_MODEL_PATH before calling.",
        "piper_package": "Piper is not installed. Install backend/requirements-piper.txt.",
        "say": "macOS say and FFmpeg are required for this adapter.",
        "ffmpeg": "FFmpeg is missing from the backend PATH.",
    }

    def __init__(self, code):
        self.public_message = self.MESSAGES[code]
        super().__init__(self.public_message)


def spoken_text(text):
    prefix = "Please confirm these details, or provide corrections: "
    if not text.startswith(prefix):
        return text
    labels = {
        "user_name": "Name", "reason_for_contact": "Reason for contact",
        "preferred_follow_up_time": "Preferred follow-up time",
        "appointment_purpose": "Appointment purpose",
        "preferred_date": "Preferred date", "preferred_time": "Preferred time",
    }
    try:
        data = json.loads(text[len(prefix):])
        if not isinstance(data, dict) or any(k not in labels or not isinstance(v, str)
                                            for k, v in data.items()):
            raise ValueError()
        return "Please confirm these details. " + ". ".join(
            labels[key] + ": " + value for key, value in data.items()) + ". Is that correct?"
    except (ValueError, TypeError) as exc:
        raise SpeechError("Invalid confirmation summary") from exc


def browser_wav(audio):
    # Pipe output can declare an unknown WAV size. Emit a standard finite header
    # for mobile decoders, and bound the actual synthesized duration.
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            rate = source.getframerate()
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or not 8000 <= rate <= 48000:
                raise SpeechError("Unsupported synthesized audio")
            frames = source.readframes(rate * 90 + 1)
            if not frames or len(frames) // 2 > rate * 90:
                raise SpeechError("Speech output duration exceeded")
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(rate)
            target.writeframes(frames)
        return output.getvalue()
    except (wave.Error, EOFError) as exc:
        raise SpeechError("Invalid synthesized audio") from exc
