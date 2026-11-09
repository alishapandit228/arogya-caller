# Windows 10/11 — ASUS VivoBook, 16 GB

One shared backend/frontend codebase. Run these PowerShell commands from your
local arogya-caller checkout; do not copy a Linux/Mac .venv. Native x64 Python
3.12 and the Windows x64 Piper wheel are the supported Windows target. Windows
ARM and real Windows hardware have not been tested by the cloud agent.

## 1. Prerequisites and installation

Install free official packages with Windows Package Manager, then open a new
PowerShell window so PATH refreshes:

```powershell
winget install --id Python.Python.3.12 --exact --source winget
winget install --id OpenJS.NodeJS.LTS --exact --source winget
winget install --id Ollama.Ollama --exact --source winget
winget install --id Gyan.FFmpeg --exact --source winget
winget install --id FiloSottile.mkcert --exact --source winget

py -3.12 --version
node --version
ffmpeg -version
ollama --version
mkcert -version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt -r backend\requirements-piper.txt
npm.cmd --prefix frontend ci
```

Node 22.12+ or 24 LTS is supported. Use npm.cmd/npx.cmd from PowerShell
to avoid npm.ps1 execution-policy errors; no policy bypass is needed. If winget is unavailable use python.org,
nodejs.org, ollama.com, ffmpeg.org's Windows build links, and the official
mkcert GitHub releases (FiloSottile/mkcert). Preserve TLS/signature verification.

Piper's maintained upstream is https://github.com/OHF-Voice/piper1-gpl.
The Python package supplies the Windows executable/native components; the app
uses that package in its own bounded worker, not an arbitrary shell command.
Piper is GPL-licensed; review upstream and the selected voice model card if
redistributing it. No executable or weights are bundled in this repository.

## 2. Explicit initial model downloads

Ollama's desktop app normally starts its loopback service. Otherwise run
ollama serve in another terminal. Do not bind it to 0.0.0.0.

```powershell
ollama pull qwen2.5:3b
Invoke-RestMethod http://127.0.0.1:11434/api/tags
.\.venv\Scripts\hf.exe download Systran/faster-whisper-tiny.en --local-dir .models/faster-whisper-tiny.en
.\.venv\Scripts\python.exe -m piper.download_voices en_US-lessac-low --data-dir .models/piper
```

Official weights: huggingface.co/Systran/faster-whisper-tiny.en and
huggingface.co/rhasspy/piper-voices (en/en_US/lessac/low). Piper needs both
en_US-lessac-low.onnx and en_US-lessac-low.onnx.json. Read that voice's MODEL_CARD.
Downloads happen only through these explicit setup commands.

Optional, after local profiling: ollama pull qwen2.5:7b, then explicitly set
OLLAMA_MODEL=qwen2.5:7b. Never assume 7B has acceptable latency just because the
machine has 16 GB RAM. For optional base.en use the explicit hf download command
with Systran/faster-whisper-base.en and a different WHISPER_MODEL_PATH.

## 3. Configuration and HTTPS certificate

Use only your private Wi-Fi. Pick the actual Wi-Fi IPv4 address, not a VPN,
loopback or virtual adapter address:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress
$LanIp = Read-Host "Enter the Mac/phone-reachable Windows Wi-Fi IPv4 address"
New-Item -ItemType Directory -Force .certs | Out-Null
mkcert -install
mkcert -cert-file .certs/local.pem -key-file .certs/local-key.pem localhost 127.0.0.1 "::1" $LanIp
$CaRoot = (& mkcert -CAROOT).Trim()
Copy-Item (Join-Path $CaRoot "rootCA.pem") .certs/arogya-development-ca.crt

$env:AI_PROFILE = "windows16"
$env:OLLAMA_MODEL = "qwen2.5:3b"
$env:OLLAMA_URL = "http://127.0.0.1:11434"
$env:WHISPER_MODEL_PATH = Join-Path $PWD ".models/faster-whisper-tiny.en"
$env:TTS_ENGINE = "auto"
$env:PIPER_MODEL_PATH = Join-Path $PWD ".models/piper/en_US-lessac-low.onnx"
$env:VOICE_COOKIE_SECURE = "true"
$env:TRUSTED_ORIGINS = '["https://' + $LanIp + ':5173","https://localhost:5173"]'
$env:DATABASE_URL = "sqlite:///./arogya.db"
$env:ADMIN_API_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
.\.venv\Scripts\python.exe backend/scripts/check_local.py
```

The checker prints only configuration metadata and prerequisite status, never
tokens. It does not download or switch models. All checks must pass before
running the real tests. Environment exports apply only to this terminal.
.env.example documents settings; an optional private .env can persist them,
but never overwrite an existing configuration or commit its secret values.
AI_PROFILE only selects a default when OLLAMA_MODEL is unset. Both Windows and
Mac defaults are 3B. No automatic performance-based model switching occurs.
PIPER_CONFIG_PATH optionally selects a different local config; otherwise it is
PIPER_MODEL_PATH plus .json. The documented offline espeak-phonemized English
voice is supported; voice choice is made by explicitly selecting its model/config.

## 4. Trust HTTPS on the phone

Transfer ONLY .certs/arogya-development-ca.crt privately to your personal test
phone. Never transfer rootCA-key.pem or local-key.pem, and never serve the
entire CA directory. On iOS install the profile under Settings > General >
VPN & Device Management, then enable its trust under General > About >
Certificate Trust Settings. On Android install it under Security > Encryption
& credentials > Install CA certificate (names vary by device).

Remove the test CA after development. Reissue the leaf certificate if the IP
changes. Do not disable certificate verification or microphone security.
Allow Node on the Windows firewall's Private network profile only if prompted.
Do not enable public-network access, router forwarding, public tunnels, or
public Ollama. Client isolation on guest Wi-Fi can prevent device communication.

## 5. Start the backend and frontend

In the configured backend terminal:

```powershell
Set-Clipboard -Value $env:ADMIN_API_TOKEN
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --ws-max-size 2048 --ws-max-queue 4
```

In a second PowerShell terminal from the same repository:

```powershell
$env:LOCAL_TLS_CERT = Join-Path $PWD ".certs/local.pem"
$env:LOCAL_TLS_KEY = Join-Path $PWD ".certs/local-key.pem"
$env:UI_HOST = "0.0.0.0"
npm.cmd --prefix frontend run dev -- --port 5173 --strictPort
```

Open https://WINDOWS_WIFI_IP:5173 on the Windows administrator device, replacing
WINDOWS_WIFI_IP with the certificate's IP. Paste the token into the sign-in;
clear the clipboard in another terminal with Set-Clipboard -Value "" afterward.
The token never goes to the phone. Frontend HTTPS proxies only /voice to the
loopback backend. Use this same IP origin to create usable phone invitations.

## 6. Real AI validation, tests and security

In a third terminal repeat the model/profile/path exports from section 3.
The tests generate their own isolated tokens/databases; check_local.py needs
ADMIN_API_TOKEN, which can be separately generated for that diagnostic command.

```powershell
Push-Location backend
try {
    ..\.venv\Scripts\python.exe -m pytest -q -m "not integration"
    $env:RUN_OLLAMA_INTEGRATION = "1"
    $env:RUN_VOICE_INTEGRATION = "1"
    ..\.venv\Scripts\python.exe -m pytest -q -m integration
} finally {
    Remove-Item Env:RUN_OLLAMA_INTEGRATION -ErrorAction SilentlyContinue
    Remove-Item Env:RUN_VOICE_INTEGRATION -ErrorAction SilentlyContinue
    Pop-Location
}
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m bandit -r backend/app backend/scripts
.\.venv\Scripts\python.exe -m pip_audit --cache-dir "$env:TEMP/arogya-audit"
npm.cmd --prefix frontend audit
.\.venv\Scripts\detect-secrets.exe scan --all-files --exclude-files '\.venv/|node_modules/|frontend/dist/|test-results/|playwright-report/|\.git/|\.cache/|\.models/|\.certs/|__pycache__/|\.pytest_cache/'
git status --short
```

Inspect each exit code; stop and diagnose failures. Real tests exercise actual
Piper → Whisper → Ollama → TTS/API → SQLite with synthetic turns, not physical
microphone acoustics. Do not substitute a passing mock result for real inference.
Optional browser automation: run npx.cmd playwright install chromium in frontend,
then npm.cmd --prefix frontend run test:browser. This test uses mocked inference.

## 7. Complete demonstration checklist

1. Confirm prerequisites and direct Ollama output; record actual model/version.
2. Sign in on the Windows dashboard; enroll a recipient with a one-use link.
3. Open the link on the trusted-HTTPS phone and keep the page visible.
4. Select the connected recipient and each role; initiate and observe ringing.
5. Reject once, then accept a new call; no AI speech must occur before acceptance.
6. Listen to the introduction, refuse consent once; then accept/consent on a new call.
7. Speak one turn at a time; test silence, denied microphone permission and retry.
8. Collect both roles; correct an ambiguous/invalid date/time and check the summary.
9. Confirm, inspect final JSON and SQLite results, then restart the backend and
   verify persistent results after signing in again.
10. End during processing and disconnect/reconnect the receiver; verify no late
    completion or leaked data. Check Task Manager, latency and sound quality
    before trying 7B or base.en. Record real device/browser results honestly.

## 8. Troubleshooting

- Command missing: open a fresh terminal, verify PATH and native x64 Python.
- Missing Piper: install requirements-piper.txt into this .venv; check both model files.
- Missing Whisper: complete the explicit tiny.en download; set an absolute path.
- Speech worker fails: verify voice/model compatibility and ffmpeg -version;
  run the opt-in real tests; never disable validation or invent speech output.
- HTTPS warning/microphone missing: correct the certificate IP and phone CA trust.
- 401/403: repeat sign-in/re-enrollment after one hour or restart; verify exact HTTPS origin.
- 429: wait for the current operation; only one call/voice computation is supported.
- No phone connection: same private Wi-Fi, correct IP, private firewall rule,
  no guest isolation; backend/Ollama should remain loopback-only.
