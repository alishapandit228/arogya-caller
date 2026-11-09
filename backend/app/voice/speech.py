"""Bounded offline speech adapters. Raw audio is never retained."""
import io
from pathlib import Path
import shutil
import subprocess  # nosec B404
import sys
import wave
from app.voice.audio import SpeechError, SpeechSetupError, browser_wav, spoken_text
from app.voice.tts import TTSAdapter


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
            raise SpeechSetupError('ffmpeg')
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
        model = Path(self.settings.whisper_model_path).expanduser()
        required = ("model.bin", "config.json", "tokenizer.json")
        if not model.is_dir() or any(not (model / name).is_file() for name in required):
            raise SpeechSetupError("whisper")
        output = self.run([sys.executable, str(Path(__file__).with_name('whisper_worker.py')),
                           self.settings.whisper_model_path], pcm, timeout=60)
        text = output.decode('utf-8').strip()
        if not text or len(text) > 2000:
            raise SpeechError('No clear speech detected; try again')
        return text

    def synthesize(self, text):
        return TTSAdapter(self.settings, self.run).synthesize(text)
