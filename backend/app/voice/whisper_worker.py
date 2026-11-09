"""A bounded-lifetime worker: release Whisper RAM before Ollama runs."""
import io
import sys
from faster_whisper import WhisperModel


def main():
    data = sys.stdin.buffer.read(700_001)
    if len(data) > 700_000:
        raise ValueError('Audio too large')
    model = WhisperModel(sys.argv[1], device='cpu', compute_type='int8', cpu_threads=2,
                         num_workers=1, local_files_only=True)
    segments, _ = model.transcribe(io.BytesIO(data), beam_size=1, language='en',
                                   vad_filter=True, condition_on_previous_text=False)
    text = ' '.join(segment.text.strip() for segment in segments).strip()
    if len(text) > 2000:
        raise ValueError('Transcript too long')
    sys.stdout.write(text)


if __name__ == '__main__':
    main()
