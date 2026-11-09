# Phase 2: local browser AI calling on macOS

This implements browser-to-backend, turn-based voice, not telephone calling.
A recipient must keep the receiving page open and connected. No background
delivery, telephone numbers, paid services, or Phase 3 integrations are included.

## Architecture and trust boundaries

React/Vite/Tailwind dashboard and mobile receiver → same-origin HTTPS proxy →
FastAPI cookie-authenticated WebSockets (signaling only) and bounded HTTP audio →
FFmpeg → faster-whisper tiny.en CPU/int8 → existing role/state/validation engine →
local Ollama qwen2.5:3b → offline macOS say → WAV → recipient speaker.

The server creates a Phase 1 session and introduction only after acceptance.
Consent/confirmation still use the Phase 1 engine; audio transcripts never
control role/schema/state directly. A receiver has no access to the Phase 1
admin API. Admin enters its token on the admin device only; it is exchanged
for a random HttpOnly cookie, never saved in browser storage or bundled code.
Recipient invitation is single-use, expires in 5 minutes, and is sent in the
URL fragment (not an HTTP URL/query log). Both scoped cookies expire in 1 hour;
re-enroll after expiry. Restart invalidates cookies; unfinished calls fail safely.
Only one receiver tab per identity and one call/model operation at a time.

This is an authenticated local-network prototype, not production identity,
clinical software, public hosting, or an emergency calling system.

## 1. Mac prerequisites and Python setup

Run from the checked-out repository root in zsh. Use a Mac-specific virtual
environment, never one copied from Linux.

Install Python 3.12 from python.org and a supported Node.js LTS (22.12+ or 24)
from nodejs.org if not installed. With Homebrew already installed from brew.sh:

```zsh
brew install ffmpeg mkcert
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt -r backend/requirements-voice.txt
npm --prefix frontend ci
ffmpeg -version
say -v '?'
ollama list
```

The default system English voice is used by macOS say. It synthesizes to a
private temporary AIFF file, which is converted to WAV and deleted. Do not
select a voice that requires downloading if offline. Linux developers may
install espeak-ng; this optional adapter is not required on macOS.

## 2. Install the free local speech recognition weights

Official converted model: https://huggingface.co/Systran/faster-whisper-tiny.en.
Download explicitly once (about 75 MB of weights), before going offline:

```zsh
HF_HOME="$PWD/.cache/huggingface" .venv/bin/hf download Systran/faster-whisper-tiny.en --local-dir .models/faster-whisper-tiny.en
export WHISPER_MODEL_PATH="$PWD/.models/faster-whisper-tiny.en"
export OLLAMA_MODEL='qwen2.5:3b'
export OLLAMA_URL='http://127.0.0.1:11434'
curl --fail --show-error http://127.0.0.1:11434/api/tags
```

If needed, start Ollama using `open -a Ollama` or `ollama serve` in another
terminal. The existing model does not need another download. Do not change its
default loopback binding. The Whisper worker uses local_files_only=True, so an
absent model fails rather than downloading during a call. Only English is
supported in this lightweight version.

The Codex cloud cannot reach the Mac's localhost. The current cloud policy
blocks the Hugging Face model destination; do not bypass it. Download on your
own permitted Mac network, or request a normal network-policy change.

## 3. Trusted HTTPS for the Mac and mobile browser

Microphone APIs require a browser-recognized secure context. Use a local
development CA and a certificate for the actual Wi-Fi IP:

```zsh
mkdir -p .certs
chmod 700 .certs
mkcert -install
# en0 is commonly Wi-Fi; check System Settings > Wi-Fi if this is empty.
LAN_IP="$(ipconfig getifaddr en0)"
test -n "$LAN_IP" || { echo 'Set LAN_IP to the Mac Wi-Fi IPv4 address'; return 1; }
mkcert -cert-file .certs/local.pem -key-file .certs/local-key.pem localhost 127.0.0.1 ::1 "$LAN_IP"
chmod 600 .certs/local-key.pem

# Copy ONLY this public CA certificate to the phone via AirDrop or another
# trusted file transfer. Never transfer rootCA-key.pem or local-key.pem.
cp "$(mkcert -CAROOT)/rootCA.pem" .certs/arogya-development-ca.crt
```

On iOS install that certificate profile (Settings → General → VPN & Device
Management), then enable trust for that installed CA under General → About →
Certificate Trust Settings. On Android use Settings → Security → Encryption &
credentials → Install a certificate → CA certificate (menu names vary).
Use a personal test device and remove the CA after development. Trust this
specific CA; do not disable browser TLS validation or click through warnings.
Never serve the CA key directory or commit any keys.

The phone and Mac must use the same private Wi-Fi without client isolation.
Reissue the leaf certificate if the Mac IP changes. macOS firewall may need to
allow the Node development server on this private network only. No router
port forwarding, public tunnel, or public Ollama exposure is needed.

## 4. Start the backend

In the same terminal holding the model exports and LAN_IP:

```zsh
export ADMIN_API_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL='sqlite:///./arogya.db'
export TRUSTED_ORIGINS="[\"https://$LAN_IP:5173\",\"https://localhost:5173\"]"
export VOICE_COOKIE_SECURE='true'
# Show the generated token ON THE ADMIN DEVICE ONLY if needed to copy into
# the dashboard password field. Never share it with a recipient or in chat.
printf '%s' "$ADMIN_API_TOKEN" | pbcopy
.venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --ws-max-size 2048 --ws-max-queue 4
```

Paste from the clipboard into the administrator sign-in on the Mac, then clear
the clipboard (`printf '' | pbcopy`). The receiver gets an invitation only.
Keep this server terminal open. Use a single worker; coordination is in memory.

## 5. Start the HTTPS frontend

In a second terminal from the repository root:

```zsh
export LOCAL_TLS_CERT="$PWD/.certs/local.pem"
export LOCAL_TLS_KEY="$PWD/.certs/local-key.pem"
export UI_HOST='0.0.0.0'
npm --prefix frontend run dev -- --port 5173 --strictPort
```

Open the dashboard on the Mac at https://MAC_WIFI_IP:5173 (replace MAC_WIFI_IP
with the IP used above). This is the same origin that invitations will use.
Vite proxies only /voice to the loopback backend, including WebSocket upgrades.
This is a LAN development server, not a production deployment. Vite preview
alone is not configured as the backend proxy.

1. Sign in with the admin token on the Mac.
2. Enter a recipient display name and create a private invitation.
3. Share that invitation privately to the phone. It expires in 5 minutes.
4. Open it on the phone, tap Connect securely, and keep the page open.
5. Select the connected recipient and agent role on the dashboard; initiate.
6. Accept or reject on the phone. Acceptance generates the introduction.
7. If autoplay is blocked, tap Play reply. Listen, then consent or decline.
8. Tap Speak and talk; pause for ~1.6 seconds to submit, or tap Send turn.
   Silence stops capture after 7 seconds; each turn stops at 19 seconds.
9. Review the transcript and AI response. Playback and recording are mutually
   exclusive. Correct ambiguous fields when asked.
10. Confirm the displayed/spoken details; the dashboard shows final JSON.
11. Test End call and rejection too. A disconnect fails the in-progress call;
    reconnection restores availability, not a lost active conversation.

Use synthetic information. The backend rejects audio beyond 2 MB / 20 seconds.
No raw uploads are stored. Current synthesized audio and limited transcript
context remain temporarily in memory. SQLite stores session data and call
metadata. Cancelled calls erase collected session fields. Confirmed results
persist. The admin can read all session results; this is not multi-tenant access.

## 6. Execute tests and audits on the Mac

Use another terminal from the repository root (exports do not carry between tabs).

```zsh
export OLLAMA_MODEL='qwen2.5:3b'
export OLLAMA_URL='http://127.0.0.1:11434'
export WHISPER_MODEL_PATH="$PWD/.models/faster-whisper-tiny.en"
(cd backend && ../.venv/bin/python -m pytest -q -m 'not integration')
npm --prefix frontend test
npm --prefix frontend run build
# Model/engine integration, explicitly REAL and expected to fail without prerequisites:
(cd backend && RUN_OLLAMA_INTEGRATION=1 RUN_VOICE_INTEGRATION=1 ../.venv/bin/python -m pytest -q -m integration)
.venv/bin/python -m bandit -r backend/app backend/scripts
.venv/bin/python -m pip_audit --cache-dir "${TMPDIR:-/tmp}/arogya-audit"
npm --prefix frontend audit
.venv/bin/detect-secrets scan --all-files --exclude-files '\.venv/|node_modules/|frontend/dist/|test-results/|\.git/|\.cache/|\.models/|\.certs/|__pycache__/|\.pytest_cache/'
git diff --check
```

The real voice test synthesizes synthetic user turns, transcribes them, drives
the real API and Ollama, then checks confirmed SQLite results after app
recreation. It does not test the phone microphone or acoustic echo.
Do the real two-device checklist above before claiming hardware/browser readiness.

Optional browser automation:

```zsh
(cd frontend && npx playwright install chromium)
npm --prefix frontend run test:browser
```

The browser test starts dedicated servers with test-only speech/model adapters
and fake Chromium microphone input. Its HTTP/WebSocket/UI/recording path is real,
but its speech/LLM content is mocked. The production factory has no fake fallback.
The test temporarily uses non-Secure cookies on loopback HTTP only; normal
deployment defaults to Secure cookies and trusted LAN HTTPS.
