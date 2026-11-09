import io
from pathlib import Path
import subprocess
import wave
import pytest
from app.core.config import Settings
from app.core.profiles import profile_name
from app.voice.audio import SpeechError
from app.voice.speech import LocalSpeech
from app.voice.tts import TTSAdapter


def settings(**kwargs):
    return Settings(admin_api_token='platform-test-' + 'x' * 40, _env_file=None, **kwargs)


def wav():
    out = io.BytesIO()
    with wave.open(out, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(b'\0\0' * 5513)
    return out.getvalue()


@pytest.mark.parametrize('system,profile,engine', [('Windows','windows16','piper'),
                                                 ('Darwin','macos8','say'),
                                                 ('Linux','portable','espeak')])
def test_platform_defaults(monkeypatch, system, profile, engine):
    monkeypatch.setattr('app.core.profiles.platform.system', lambda: system)
    monkeypatch.setattr('app.voice.tts.shutil.which', lambda name: '/local/' + name)
    value = settings()
    assert profile_name('auto') == profile
    assert value.ollama_model == 'qwen2.5:3b'
    assert TTSAdapter(value, None).engine() == engine


@pytest.mark.parametrize('profile,model', [('windows16','qwen2.5:7b'), ('macos8','qwen2.5:1.5b')])
def test_explicit_model_override(profile, model):
    assert settings(ai_profile=profile, ollama_model=model).ollama_model == model


def test_invalid_profile_or_engine():
    for value in [{'ai_profile': 'huge'}, {'tts_engine': 'cloud'}, {'ollama_model': ''}]:
        with pytest.raises(ValueError):
            settings(**value)


def test_windows_piper_arguments_output_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr('app.voice.tts.platform.system', lambda: 'Windows')
    monkeypatch.setattr('app.voice.tts.importlib.util.find_spec', lambda name: object())
    model = tmp_path / 'voice with spaces.onnx'
    model.touch()
    config = Path(str(model) + '.json')
    config.write_text('{}')
    outputs = []
    def run(args, text, timeout):
        assert Path(args[1]).name == 'piper_worker.py'
        assert args[2:4] == [str(model), str(config)]
        assert text == b'Hello; $(do not execute)'
        assert timeout == 60
        outputs.append(Path(args[4]))
        outputs[-1].write_bytes(wav())
    result = TTSAdapter(settings(piper_model_path=str(model)), run).synthesize('Hello; $(do not execute)')
    assert result.startswith(b'RIFF')
    assert not outputs[0].exists() and not outputs[0].parent.exists()


def test_piper_timeout_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr('app.voice.tts.importlib.util.find_spec', lambda name: object())
    model = tmp_path / 'voice.onnx'
    model.touch()
    Path(str(model) + '.json').write_text('{}')
    outputs = []
    def run(args, text, timeout):
        outputs.append(Path(args[4]))
        outputs[-1].write_bytes(b'partial')
        raise SpeechError('timeout')
    with pytest.raises(SpeechError):
        TTSAdapter(settings(tts_engine='piper', piper_model_path=str(model)), run).synthesize('Hello')
    assert not outputs[0].parent.exists()


@pytest.mark.parametrize('package,files', [(False,False),(True,False)])
def test_missing_piper_dependencies(tmp_path, monkeypatch, package, files):
    monkeypatch.setattr('app.voice.tts.importlib.util.find_spec', lambda name: object() if package else None)
    with pytest.raises(SpeechError) as error:
        TTSAdapter(settings(tts_engine='piper', piper_model_path=str(tmp_path/'absent.onnx')), None).synthesize('Hello')
    assert error.value.public_message
    assert 'not installed' in str(error.value) if not package else 'missing' in str(error.value)


def test_mac_voice_selection_and_cleanup(monkeypatch):
    monkeypatch.setattr('app.voice.tts.platform.system', lambda: 'Darwin')
    monkeypatch.setattr('app.voice.tts.shutil.which', lambda name: '/local/' + name)
    output = []
    def run(args, data=None, timeout=15):
        if args[0].endswith('/say'):
            assert args[-2:] == ['-v', 'Samantha']
            output.append(Path(args[2]))
            output[-1].touch()
            return b''
        assert str(output[-1]) in args
        return wav()
    assert TTSAdapter(settings(tts_voice='Samantha'), run).synthesize('Hello').startswith(b'RIFF')
    assert not output[0].parent.exists()


def test_missing_mac_executable(monkeypatch):
    monkeypatch.setattr('app.voice.tts.platform.system', lambda: 'Darwin')
    monkeypatch.setattr('app.voice.tts.shutil.which', lambda name: None)
    with pytest.raises(SpeechError):
        TTSAdapter(settings(tts_engine='say'), None).synthesize('Hello')


def test_mac_auto_piper_fallback(monkeypatch):
    monkeypatch.setattr('app.voice.tts.platform.system', lambda: 'Darwin')
    monkeypatch.setattr('app.voice.tts.shutil.which', lambda name: None)
    assert TTSAdapter(settings(), None).engine() == 'piper'


def test_wrong_platform_adapter(monkeypatch):
    monkeypatch.setattr('app.voice.tts.platform.system', lambda: 'Windows')
    for engine in ['say', 'espeak']:
        with pytest.raises(SpeechError):
            TTSAdapter(settings(tts_engine=engine), None).synthesize('Hello')


def test_whisper_missing_weights_is_explicit(tmp_path, monkeypatch):
    speech = LocalSpeech(settings(whisper_model_path=str(tmp_path/'absent')))
    monkeypatch.setattr(speech, 'decode', lambda audio: wav())
    with pytest.raises(SpeechError, match='Whisper weights are missing'):
        speech.transcribe(wav())


def test_safe_subprocess_timeout(monkeypatch):
    def fail(args, **kwargs):
        assert kwargs.get('shell', False) is False
        assert kwargs['timeout'] == 15
        raise subprocess.TimeoutExpired(args, 15)
    monkeypatch.setattr('app.voice.speech.subprocess.run', fail)
    with pytest.raises(SpeechError, match='unavailable'):
        LocalSpeech(settings()).run(['/trusted/ffmpeg'], b'input')


def load_worker(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1]/'app'/'voice'/f'{name}.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


def test_whisper_worker_cpu_offline_and_utf8(tmp_path, monkeypatch):
    from types import SimpleNamespace
    worker = load_worker('whisper_worker')
    captured = {}
    class Model:
        def __init__(self, path, **kwargs):
            captured.update(kwargs)
        def transcribe(self, data, **kwargs):
            assert kwargs['beam_size'] == 1 and kwargs['vad_filter']
            return [SimpleNamespace(text='Hello, José')], None
    monkeypatch.setattr(worker, 'WhisperModel', Model)
    out = io.BytesIO()
    monkeypatch.setattr(worker, 'sys', SimpleNamespace(argv=['worker',str(tmp_path)],
        stdin=SimpleNamespace(buffer=io.BytesIO(wav())), stdout=SimpleNamespace(buffer=out)))
    worker.main()
    assert out.getvalue().decode('utf-8') == 'Hello, José'
    assert captured['device'] == 'cpu' and captured['compute_type'] == 'int8'
    assert captured['local_files_only'] and captured['cpu_threads'] == 2


def test_piper_worker_local_cpu_api(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    worker = load_worker('piper_worker')
    model, config, output = tmp_path/'voice.onnx', tmp_path/'voice.json', tmp_path/'out.wav'
    model.touch()
    config.write_text('{"phoneme_type":"espeak"}')
    class Voice:
        @staticmethod
        def load(path, **kwargs):
            assert path == model and kwargs == {'config_path':config, 'use_cuda':False}
            return Voice()
        def synthesize_wav(self, text, target):
            assert text == 'Hello'
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(22050)
            target.writeframes(b'\0\0'*100)
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=Voice))
    monkeypatch.setattr(worker, 'sys', SimpleNamespace(argv=['worker',str(model),str(config),str(output)],
                         stdin=SimpleNamespace(buffer=io.BytesIO(b'Hello'))))
    worker.main()
    assert output.read_bytes().startswith(b'RIFF')
    config.write_text('{"phoneme_type":"unapproved-downloader"}')
    worker.sys.stdin.buffer = io.BytesIO(b'Hello')
    with pytest.raises(ValueError, match='documented offline'):
        worker.main()
