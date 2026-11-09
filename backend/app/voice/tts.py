"""OS-aware offline TTS; missing dependencies fail rather than trigger downloads."""
import importlib.util
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from app.voice.audio import SpeechError, SpeechSetupError, browser_wav, spoken_text


class TTSAdapter:
    def __init__(self, settings, run):
        self.settings, self.run = settings, run

    def engine(self):
        selected = self.settings.tts_engine
        system = platform.system()
        if selected == 'auto':
            if system == 'Windows':
                return 'piper'
            if system == 'Darwin':
                return 'say' if shutil.which('say') else 'piper'
            return 'espeak'
        if selected == 'say' and system != 'Darwin':
            raise SpeechError('The say adapter requires macOS')
        if selected == 'espeak' and system not in {'Linux', 'FreeBSD'}:
            raise SpeechError('Use Piper on Windows, or say/Piper on macOS')
        return selected

    def synthesize(self, text):
        text = spoken_text(text)
        if not text or len(text) > 1800:
            raise SpeechError('Speech output too long')
        engine = self.engine()
        if engine == 'piper':
            if importlib.util.find_spec('piper') is None:
                raise SpeechSetupError('piper_package')
            model = Path(self.settings.piper_model_path).expanduser().resolve()
            config = Path(self.settings.piper_config_path or str(model) + '.json').expanduser().resolve()
            if not model.is_file() or not config.is_file():
                raise SpeechSetupError('piper_model')
            with tempfile.TemporaryDirectory(prefix='arogya-tts-') as directory:
                output = Path(directory) / 'speech.wav'
                self.run([sys.executable, str(Path(__file__).with_name('piper_worker.py')),
                          str(model), str(config), str(output)], text.encode('utf-8'), timeout=60)
                if not output.is_file() or output.stat().st_size > 5_000_000:
                    raise SpeechError('Piper returned missing or oversized audio')
                audio = output.read_bytes()
        elif engine == 'say':
            say, ffmpeg = shutil.which('say'), shutil.which('ffmpeg')
            if not say or not ffmpeg:
                raise SpeechSetupError('say')
            with tempfile.TemporaryDirectory(prefix='arogya-tts-') as directory:
                path = str(Path(directory) / 'speech.aiff')
                args = [say, '-o', path]
                if self.settings.tts_voice:
                    args += ['-v', self.settings.tts_voice]
                self.run(args, text.encode('utf-8'), timeout=30)
                audio = self.run([ffmpeg, '-v', 'error', '-nostdin', '-i', path,
                                  '-t', '90', '-ac', '1', '-ar', '22050', '-f', 'wav', 'pipe:1'])
        else:
            espeak = shutil.which('espeak') or shutil.which('espeak-ng')
            if not espeak:
                raise SpeechError('Install espeak-ng, or explicitly configure Piper')
            args = [espeak, '--stdout', '--stdin']
            if self.settings.tts_voice:
                args += ['-v', self.settings.tts_voice]
            audio = self.run(args, text.encode('utf-8'), timeout=30)
        if len(audio) > 5_000_000:
            raise SpeechError('Speech output too large')
        return browser_wav(audio)
