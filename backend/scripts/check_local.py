"""Read-only local prerequisites check. Never downloads or prints credentials."""
import importlib.util
from pathlib import Path
import platform
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.core.config import Settings
from app.core.profiles import profile_name
from app.voice.tts import TTSAdapter


def main():
    try:
        settings = Settings()
    except ValueError:
        print('FAIL: configuration invalid; configure ADMIN_API_TOKEN and check .env.example')
        return 1
    missing = []
    def check(name, valid):
        print(('PASS: ' if valid else 'FAIL: ') + name)
        if not valid:
            missing.append(name)
    print('Platform:', platform.system(), '| profile:', profile_name(settings.ai_profile),
          '| selected model:', settings.ollama_model)
    check('FFmpeg on PATH', shutil.which('ffmpeg') is not None)
    model = Path(settings.whisper_model_path).expanduser()
    check('Local Whisper weights', all((model / f).is_file() for f in ['model.bin','config.json','tokenizer.json']))
    check('faster-whisper package', importlib.util.find_spec('faster_whisper') is not None)
    try:
        engine = TTSAdapter(settings, None).engine()
        print('Selected TTS:', engine)
        if engine == 'piper':
            check('Piper package', importlib.util.find_spec('piper') is not None)
            model = Path(settings.piper_model_path).expanduser()
            config = Path(settings.piper_config_path or str(model) + '.json').expanduser()
            check('Local Piper voice and config', model.is_file() and config.is_file())
        else:
            check('Installed TTS executable', shutil.which('say' if engine == 'say' else 'espeak') is not None
                  or engine == 'espeak' and shutil.which('espeak-ng') is not None)
    except Exception:
        check('Compatible TTS configuration', False)
    try:
        with httpx.Client(base_url=settings.ollama_url, timeout=5, trust_env=False) as client:
            response = client.get('/api/tags')
            response.raise_for_status()
            check('Selected model installed in local Ollama',
                  settings.ollama_model in {m['name'] for m in response.json()['models']})
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        check('Local Ollama API accessible', False)
    print('No downloads or model switching performed. Run real integration tests after all checks pass.')
    return int(bool(missing))


if __name__ == '__main__':
    sys.exit(main())
