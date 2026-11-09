# macOS — MacBook Air, 8 GB

Same application as Windows. macOS defaults to the installed say adapter, with
Piper available only when explicitly installed/configured. Hardware validation
has not been performed from the Linux cloud workspace.

## 1. Prerequisites and dependencies

Use Python 3.12 from python.org, Node 22.12+ or 24 LTS from nodejs.org, and
Ollama from ollama.com. With Homebrew already installed from brew.sh:

```zsh
brew install ffmpeg mkcert
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt -r backend/requirements-voice.txt
npm --prefix frontend ci
ffmpeg -version
say -v '?'
ollama --version
```

Run from the repository root; never reuse a Windows/Linux virtual environment.
Keep macOS say's default installed English voice to avoid a voice download.

## 2. Explicit initial model downloads

```zsh
ollama pull qwen2.5:3b
HF_HOME="$PWD/.cache/huggingface" .venv/bin/hf download Systran/faster-whisper-tiny.en --local-dir .models/faster-whisper-tiny.en
export AI_PROFILE='macos8'
export OLLAMA_MODEL='qwen2.5:3b'
export OLLAMA_URL='http://127.0.0.1:11434'
export WHISPER_MODEL_PATH="$PWD/.models/faster-whisper-tiny.en"
export TTS_ENGINE='auto'
# Optional installed system voice; inspect say -v '?' first:
# export TTS_VOICE='Samantha'
```

If stopped, open -a Ollama or run ollama serve in a separate terminal.
Do not expose Ollama to the LAN. Existing weights need not be downloaded again.
Official Whisper source: huggingface.co/Systran/faster-whisper-tiny.en.
Inference is CPU/int8 with two threads, local files only. Each Whisper process
exits before the Ollama request. One active call/computation is supported.

If 3B is too slow or RAM is pressured, explicitly run ollama pull qwen2.5:1.5b
and export OLLAMA_MODEL='qwen2.5:1.5b'. Nothing switches automatically.
Optional base.en requires an explicit Systran/faster-whisper-base.en download
and WHISPER_MODEL_PATH change; benchmark it before use on 8 GB RAM.

Optional Piper (not needed for say):

```zsh
.venv/bin/python -m pip install -r backend/requirements-piper.txt
.venv/bin/python -m piper.download_voices en_US-lessac-low --data-dir .models/piper
export TTS_ENGINE='piper'
export PIPER_MODEL_PATH="$PWD/.models/piper/en_US-lessac-low.onnx"
```

Official package/docs: github.com/OHF-Voice/piper1-gpl; voice:
huggingface.co/rhasspy/piper-voices/en/en_US/lessac/low. Review GPL and the
voice's MODEL_CARD if redistributing. Both ONNX and adjacent .onnx.json are
required; optional PIPER_CONFIG_PATH overrides the latter. The documented
offline espeak-phonemized English voices are supported. No binaries/weights
are included in Git. Auto uses say when installed, otherwise requires Piper;
it never installs an adapter or downloads a voice during a call.

## 3. Configuration and trusted LAN HTTPS

```zsh
mkdir -p .certs
chmod 700 .certs
mkcert -install
LAN_IP="$(ipconfig getifaddr en0)"
# If empty, use the Wi-Fi address in System Settings and set LAN_IP manually.
mkcert -cert-file .certs/local.pem -key-file .certs/local-key.pem localhost 127.0.0.1 ::1 "$LAN_IP"
chmod 600 .certs/local-key.pem
cp "$(mkcert -CAROOT)/rootCA.pem" .certs/arogya-development-ca.crt
export ADMIN_API_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL='sqlite:///./arogya.db'
export TRUSTED_ORIGINS="[\"https://$LAN_IP:5173\",\"https://localhost:5173\"]"
export VOICE_COOKIE_SECURE='true'
.venv/bin/python backend/scripts/check_local.py
```

The checker is read-only, reports missing weights/executables/model, and prints
no token. AI_PROFILE determines a default only when OLLAMA_MODEL is unset.
An optional ignored .env can persist configuration; do not overwrite an existing
file or commit credentials. Exports belong to the current terminal only.

## 4. Phone certificate trust

Transfer ONLY .certs/arogya-development-ca.crt privately. Never share
rootCA-key.pem or local-key.pem, never serve the CA directory, and never commit
certificates. On iOS install the profile under General > VPN & Device Management
and enable that CA under General > About > Certificate Trust Settings.
On Android use Security > Encryption & credentials > Install CA certificate.

Use a personal test device; remove the CA afterward. Reissue the certificate
when the Mac's IP changes. Keep Mac/phone on the same private Wi-Fi, without
client isolation. Allow Node only on that private network if the firewall asks.
Do not bypass TLS/microphone rules, forward router ports, or use public tunnels.

## 5. Start both services

In the configured backend terminal:

```zsh
printf '%s' "$ADMIN_API_TOKEN" | pbcopy
.venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --ws-max-size 2048 --ws-max-queue 4
```

In a second terminal at the same repository root:

```zsh
export LOCAL_TLS_CERT="$PWD/.certs/local.pem"
export LOCAL_TLS_KEY="$PWD/.certs/local-key.pem"
export UI_HOST='0.0.0.0'
npm --prefix frontend run dev -- --port 5173 --strictPort
```

Open https://MAC_WIFI_IP:5173 on the Mac (replace with the certificate's IP).
Paste the admin token into sign-in, then clear the clipboard in another terminal
with printf '' | pbcopy. Use the IP origin, not localhost, for invitations to
the phone. Frontend HTTPS proxies only /voice to the loopback FastAPI backend.
The recipient never receives the admin token.

## 6. Real voice validation and audit

In another terminal repeat the model/profile/path/TTS exports above first;
terminal exports do not automatically carry over. Real tests use their own
temporary database and admin token.

```zsh
(cd backend && ../.venv/bin/python -m pytest -q -m 'not integration')
(cd backend && RUN_OLLAMA_INTEGRATION=1 RUN_VOICE_INTEGRATION=1 ../.venv/bin/python -m pytest -q -m integration)
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m bandit -r backend/app backend/scripts
.venv/bin/python -m pip_audit --cache-dir "${TMPDIR:-/tmp}/arogya-audit"
npm --prefix frontend audit
.venv/bin/detect-secrets scan --all-files --exclude-files '\.venv/|node_modules/|frontend/dist/|test-results/|playwright-report/|\.git/|\.cache/|\.models/|\.certs/|__pycache__/|\.pytest_cache/'
git status --short
```

Inspect failures individually. The real tests cover local speech roundtrip and
API → STT → Ollama → TTS → confirmation → SQLite with synthetic audio. They do
not measure physical microphone/speaker acoustics. Optional browser automation:
(cd frontend && npx playwright install chromium), then
npm --prefix frontend run test:browser; inference is mocked in that test.

## 7. Complete demonstration checklist

1. Verify check_local.py, Ollama version/model, and actual system/Piper voice.
2. Sign in to the Mac dashboard and enroll a recipient via a one-use link.
3. Open the link on a trusted-HTTPS phone; keep it visible and connected.
4. Select each role and recipient; initiate and observe incoming ringing.
5. Reject once, then accept a new call; verify no agent speech before acceptance.
6. Listen to AI identification/purpose, refuse consent once, then test consent.
7. Speak naturally turn by turn; test silence, permission denial, and playback retry.
8. Exercise both roles, ambiguous answers, invalid dates/times, and corrections.
9. Review/confirm the summary; inspect JSON, restart and reauthenticate, verify SQLite persistence.
10. End during processing and disconnect/reconnect; ensure no late completion.
    Record Activity Monitor RAM, latency, browser and audio quality before trying
    base.en. If switching to 1.5B, explicitly record and retest that selected model.

## 8. Troubleshooting

- Missing voice/weights: select an installed say voice or install both Piper
  files; ensure WHISPER_MODEL_PATH points to the completed local converted model.
- Missing command: inspect PATH and use the interpreter in this .venv.
- No speech/slow response: run real tests; check local logs without sharing
  tokens or personal data; close memory-heavy apps. Do not substitute canned output.
- Microphone/TLS failure: correct CA trust, actual Wi-Fi IP/SAN, and browser permissions.
- 401/403: re-sign in/re-enroll after expiry/restart; verify exact HTTPS Origin.
- 429: only one operation/call is allowed; wait before retrying.
- Reconnection: refresh/re-enroll when expired; interrupted calls fail and must
  be initiated again. No background receiving is supported.
