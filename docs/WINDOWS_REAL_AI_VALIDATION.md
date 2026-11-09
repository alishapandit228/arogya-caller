# Windows: real Phase 1 AI validation

The attached Codex executor is a remote Linux machine. Its localhost is not
your Windows laptop's localhost. A blocked download there does not establish
any restriction on your laptop. This guide runs everything on Windows using
free official software; it does not expose Ollama to the network.

## 1. Inspect the laptop

Open Windows PowerShell:

```powershell
Get-Command ollama -ErrorAction SilentlyContinue
$ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
Test-Path $ollamaExe
# If PATH lookup fails but Test-Path is True, use the existing installation:
if (-not (Get-Command ollama -ErrorAction SilentlyContinue) -and (Test-Path $ollamaExe)) {
    $env:Path = (Split-Path $ollamaExe) + ";" + $env:Path
}
ollama --version
ollama list
```

A command-not-found error indicates no installation on PATH, not a download
policy failure. A connection error from ollama list can mean the server is stopped.

## 2. Install only if missing

Official download page: https://ollama.com/download/windows.
For the graphical installer from that official source:

```powershell
$installer = Join-Path $env:TEMP "OllamaSetup.exe"
Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer
$signature = Get-AuthenticodeSignature $installer
$signature | Select-Object Status, StatusMessage
if ($signature.Status -ne "Valid") {
    throw "Installer signature verification failed. Do not run this file."
}
Start-Process -FilePath $installer -Wait
```

Complete the installer normally, then open a new PowerShell window and run
`ollama --version`. Alternatively download the Windows installer directly from
the official page in your browser and inspect Properties → Digital Signatures.
Do not disable certificate/signature verification.

If the laptop's download is also explicitly blocked by its organization or
network, stop and ask that network's administrator to permit the official
destination. Do not use mirrors, bypass proxies, or disable firewall protections.

## 3. Start the local server and inspect models

The Windows Ollama app normally starts the server. If this probe fails, start
the installed Ollama app, or run `ollama serve` in a separate terminal.
An "address already in use" message usually means a server is already running;
probe it instead of starting another one.

```powershell
Invoke-RestMethod "http://127.0.0.1:11434/api/version"
$models = Invoke-RestMethod "http://127.0.0.1:11434/api/tags"
$models.models | Select-Object name, size
```

Do not set OLLAMA_HOST to 0.0.0.0. Keep both services on loopback.

## 4. Download the model only if absent, then send a real prompt

Official model page: https://ollama.com/library/qwen2.5:1.5b.
Ollama's supported manual download command uses the official registry and
verifies downloaded content. No separately sourced GGUF or paid API is needed.

```powershell
ollama list
# Run only if qwen2.5:1.5b is not listed:
ollama pull qwen2.5:1.5b
if ($LASTEXITCODE -ne 0) { throw "Model pull failed; preserve the error for diagnosis." }
ollama show qwen2.5:1.5b

$body = @{
    model = "qwen2.5:1.5b"
    prompt = "Identify yourself briefly as a local AI assistant."
    stream = $false
    options = @{ temperature = 0; num_predict = 64; num_ctx = 2048 }
} | ConvertTo-Json -Depth 4
$reply = Invoke-RestMethod "http://127.0.0.1:11434/api/generate" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 120
if (-not $reply.done -or [string]::IsNullOrWhiteSpace($reply.response)) {
    throw "The model did not return a completed nonempty response."
}
$reply.response
```

If model download fails, share the exact error and hostname, without credentials.
Ollama model pulls contact registry.ollama.ai and may follow official storage/CDN
redirects. Only an observed error can establish which destination needs review.
An installation on your laptop does not automatically make its server available
to the remote Codex executor. Do not publicly expose it to solve that separation.

## 5. Run the repository locally

The new files must first exist in your laptop's VS Code workspace. This session
has not committed or pushed them. Transfer the prepared working files through
your approved workspace/file workflow if your laptop does not already have them.
Run the following from your local arogya-caller repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Push-Location backend
try {
    ..\.venv\Scripts\python.exe -m pytest -q -m "not integration"
    if ($LASTEXITCODE -ne 0) { throw "Mocked tests failed." }
    $env:RUN_OLLAMA_INTEGRATION = "1"
    ..\.venv\Scripts\python.exe -m pytest -q -m integration
    if ($LASTEXITCODE -ne 0) { throw "Real AI validation failed. Keep the test output." }
} finally {
    Remove-Item Env:RUN_OLLAMA_INTEGRATION -ErrorAction SilentlyContinue
    Pop-Location
}
```

The four real tests run an actual prompt, both role conversations, and refusal.
They assert consent, role preservation, one-question limits, progressive
extraction, pending confirmation, no premature result, completion, and SQLite
persistence across app recreation. Synthetic data and a temporary database/token
are used; no real personal information is needed. No model responses are mocked.
A failed semantic assertion is evidence to diagnose, not a reason to skip it.

On 8 GB RAM use one model/request at a time, close memory-heavy applications,
and allow the model to warm up. If the 90-second backend timeout is insufficient,
report the actual timing rather than weakening tests or silently substituting answers.

## 6. Security checks and interactive use

```powershell
.\.venv\Scripts\python.exe -m bandit -r backend/app
.\.venv\Scripts\python.exe -m pip_audit --cache-dir "$env:TEMP\arogya-audit"
.\.venv\Scripts\detect-secrets.exe scan --all-files --exclude-files '\.venv/|\.git/|__pycache__/|\.pytest_cache/'
git diff --check
git status --short
```

See README.md for the authenticated interactive API walkthrough. All automated
conversation tests use real API handlers with SQLite; the separate direct prompt
test exercises the real Ollama HTTP service.

Share the version, model listing, synthetic prompt response, pytest summary and
any failure output. Never share your admin token, .env contents, or real user data.
Real validation is complete only once these real tests pass; afterward stop for
user confirmation. No Phase 2, commit, or push is authorized.
