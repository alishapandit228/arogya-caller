"""Bounded offline speech adapters. Raw audio is never retained."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import wave


class SpeechError(Exception):
    pass


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


class LocalSpeech:
    def __init__(self, settings):
        self.settings = settings

    def run(self, args, data=None, timeout=15):
        # Fixed executables/arguments, no shell; untrusted data travels on stdin.
        try:
            result = subprocess.run(args, input=data, capture_output=True, timeout=timeout,
                                    check=True)  # nosec B603
            return result.stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise SpeechError('Local speech processing unavailable') from exc

    def decode(self, audio):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise SpeechError('FFmpeg is required')
        pcm = self.run([ffmpeg, '-v', 'error', '-xerror', '-nostdin', '-protocol_whitelist', 'pipe',
                        '-i', 'pipe:0', '-t', '21', '-ac', '1', '-ar', '16000',
                        '-f', 'wav', 'pipe:1'], audio)
        try:
            with wave.open(io.BytesIO(pcm)) as source:
                # FFmpeg pipe WAV headers can have unknown lengths: bound actual bytes.
                samples = source.readframes(16000 * 21)
                if not 1600 <= len(samples) // 2 <= 16000 * 20:
                    raise SpeechError('Record between 0.1 and 20 seconds')
        except (wave.Error, EOFError) as exc:
            raise SpeechError('Invalid audio') from exc
        clean = io.BytesIO()
        with wave.open(clean, 'wb') as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(16000)
            target.writeframes(samples)
        return clean.getvalue()

    def transcribe(self, audio):
        pcm = self.decode(audio)
        output = self.run([sys.executable, str(Path(__file__).with_name('whisper_worker.py')),
                           self.settings.whisper_model_path], pcm, timeout=60)
        text = output.decode('utf-8').strip()
        if not text or len(text) > 2000:
            raise SpeechError('No clear speech detected; try again')
        return text

    def synthesize(self, text):
        text = spoken_text(text)
        if not text or len(text) > 1800:
            raise SpeechError('Speech output too long')
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise SpeechError('FFmpeg is required')
        if sys.platform == 'darwin':
            say = shutil.which('say')
            if not say:
                raise SpeechError('macOS say is unavailable')
            with tempfile.TemporaryDirectory(prefix='arogya-tts-') as directory:
                path = str(Path(directory) / 'speech.aiff')
                self.run([say, '-o', path], text.encode(), timeout=30)
                audio = self.run([ffmpeg, '-v', 'error', '-nostdin', '-i', path,
                                  '-t', '90', '-ac', '1', '-ar', '22050', '-f', 'wav', 'pipe:1'])
        else:
            espeak = shutil.which('espeak') or shutil.which('espeak-ng')
            if not espeak:
                raise SpeechError('Install espeak-ng, or use macOS say')
            audio = self.run([espeak, '--stdout', '--stdin'], text.encode(), timeout=30)
        if len(audio) > 5_000_000:
            raise SpeechError('Speech output too large')
        return browser_wav(audio)
