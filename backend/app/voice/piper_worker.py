"""One offline CPU synthesis process; never download or retain voice resources."""
from pathlib import Path
import json
import sys
import wave


def main():
    model, config, output = map(Path, sys.argv[1:4])
    if not model.is_file() or not config.is_file():
        raise ValueError('Local Piper model and config are required')
    text = sys.stdin.buffer.read(7201).decode('utf-8')
    if not text or len(text) > 1800:
        raise ValueError('Invalid speech text')
    data = json.loads(config.read_text(encoding="utf-8"))
    if data.get("phoneme_type", "espeak") != "espeak":
        raise ValueError("Use the documented offline espeak English Piper voice")
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from piper import PiperVoice
    voice = PiperVoice.load(model, config_path=config, use_cuda=False)
    with wave.open(str(output), 'wb') as wav:
        voice.synthesize_wav(text, wav)


if __name__ == '__main__':
    main()
