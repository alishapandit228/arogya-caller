# Arogya Caller

**Current work: Phase 3 cross-platform integration.** One shared application
targets Windows 10/11 x64 (16 GB) and macOS (8 GB). Start with
[Windows PowerShell setup](docs/WINDOWS_SETUP.md) or
[macOS zsh setup](docs/MACOS_SETUP.md), then read the
[Phase 3 engineering/security report](docs/PHASE3_REPORT.md).
Windows uses offline Piper; Mac uses installed say or optional Piper.
Both default to local qwen2.5:3b, with explicit profile/model overrides and
no automatic downloads during calls. Real hardware validation remains pending.

The Phase 1 and Phase 2 sections/reports below are preserved as history;
the OS-specific Phase 3 guides are the current startup instructions.

A free, locally runnable, role-based AI information collection backend. Phase 1
implements text conversations to validate the logic for a future browser voice
calling product. It does not make calls or book appointments.

## Phase 1 implementation

- FastAPI REST API, protected with one administrator Bearer token.
- Trusted, immutable Python role configurations: general information and appointment requests.
- Local Ollama chat and extraction using `qwen2.5:1.5b`; no paid/cloud AI.
- Consent, clarification, deterministic field validation, explicit confirmation,
  cancellation, and terminal-state protection.
- SQLite persistence through SQLAlchemy. UUID session identifiers.
- Bounded in-memory conversation context; no transcripts/audio stored in SQLite.
- Mocked API tests, opt-in real model integration test, and security checks.

Architecture: REST API → state machine + trusted role → local Ollama →
Pydantic validation → SQLAlchemy/SQLite. The model proposes facts and questions;
Python controls state and completion. Modules live under `backend/app/`:
`agents`, `core`, `models`, `schemas`, and `services`. Routes and auth are
in `main.py`; tests in `backend/tests`.

For laptop diagnostics, official installation/model download steps, and the expanded
real-model checks, follow [Windows real AI validation](docs/WINDOWS_REAL_AI_VALIDATION.md).
The cloud executor cannot inspect or connect to your laptop through localhost.

For the current macOS/zsh setup with qwen2.5:3b, use
[macOS real AI validation](docs/MACOS_REAL_AI_VALIDATION.md). It includes a real
HTTP conversation runner that checks SQLite across a backend process restart.

## Requirements

Windows, PowerShell, Python 3.12, Git, and Ollama for Windows from
https://ollama.com/download/windows. An 8 GB machine should use the 1.5B model,
one request at a time, and close memory-heavy applications. Model download
requires Internet access and disk space; execution is local and free.
No Docker, Redis, paid APIs, credit card, or cloud hosting is required.

## Windows PowerShell setup

Run from the repository root. Activation is unnecessary.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
$env:ADMIN_API_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
$env:DATABASE_URL = "sqlite:///./arogya.db"
$env:OLLAMA_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen2.5:1.5b"
$env:TRUSTED_ORIGINS = "[]"
ollama pull qwen2.5:1.5b
ollama list
```

Ollama's Windows application normally runs the local server. If it is not
running, open a separate PowerShell window and run `ollama serve`. Keep its
default loopback binding. Do not expose either server to the LAN.

The generated token exists only in the current PowerShell environment.
Never print, share, or commit it. Generate a new one for another working session,
or store it securely in a local environment configuration. `.env.example`
documents supported variables; copying it is optional. A local `.env` is loaded
from the current working directory and must never be committed. At least 32
characters are required; the documented generator supplies cryptographic entropy.

Start from the root (keep this working directory so database paths are stable):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Do not use multiple workers: the small local prototype serializes AI calls
with an in-process lock. SQLite tables are created at startup.

## API walkthrough

Use the same PowerShell environment that holds the admin token, while the
server runs in another terminal with that token configured.

```powershell
$base = "http://127.0.0.1:8000"
$headers = @{ Authorization = "Bearer $env:ADMIN_API_TOKEN" }
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/roles" -Headers $headers
$session = Invoke-RestMethod "$base/sessions" -Method Post -Headers $headers -ContentType "application/json" -Body '{"role_id":"appointment"}'
$id = $session.id
$session.message
Invoke-RestMethod "$base/sessions/$id/reply" -Method Post -Headers $headers -ContentType "application/json" -Body '{"message":"Yes, I consent."}'
Invoke-RestMethod "$base/sessions/$id/reply" -Method Post -Headers $headers -ContentType "application/json" -Body '{"message":"Annual checkup on December 20, 2099 at 10:30 AM"}'
# Read the returned question/summary. Answer clarification questions as needed.
Invoke-RestMethod "$base/sessions/$id/reply" -Method Post -Headers $headers -ContentType "application/json" -Body '{"message":"Yes, these details are correct."}'
Invoke-RestMethod "$base/sessions/$id/result" -Headers $headers
Invoke-RestMethod "$base/sessions?limit=20&offset=0" -Headers $headers
# For a different, unfinished session:
# Invoke-RestMethod "$base/sessions/$id/cancel" -Method Post -Headers $headers
```

| Method | Path | Behavior |
|---|---|---|
| GET | /health | Public liveness; does not assert model readiness |
| GET | /roles | Trusted role metadata |
| POST | /sessions | Create with role_id; returns 201 and consent greeting |
| POST | /sessions/{id}/reply | Submit message and return state/question |
| GET | /sessions/{id} | Current state and validated data |
| GET | /sessions/{id}/result | Confirmed result only |
| GET | /sessions | Bounded paginated admin listing |
| POST | /sessions/{id}/cancel | Cancel unfinished session and erase collected data |

All endpoints except health require the admin token. Errors use
`{"error":"..."}`; validation errors omit submitted values.
401 = authentication, 404 = missing session, 409 = invalid state/unconfirmed
result, 413/422 = invalid input, 429 = AI engine busy, 503 = failed model call.
A model failure marks the session failed; create a new session. Cancellation
through the dedicated endpoint works without Ollama.

States: created → awaiting_consent → active → completed. Awaiting/active may
be cancelled or failed; terminal states cannot be modified.
Consent and confirmation require model interpretation AND an explicit phrase:
`yes`, `yes, I consent`, `I consent`, `I agree`, `confirm`, `confirmed`,
or `yes, these details are correct` (case-insensitive, optional final punctuation).
Consent-stage messages never save extracted fields. Summary confirmation requires
a subsequent reply; a model cannot complete a session on the same turn as extraction.

## Tests and security commands

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q -m "not integration"
$env:RUN_OLLAMA_INTEGRATION = "1"
..\.venv\Scripts\python.exe -m pytest -q -m integration
Remove-Item Env:RUN_OLLAMA_INTEGRATION
Pop-Location
.\.venv\Scripts\python.exe -m bandit -r backend/app
.\.venv\Scripts\python.exe -m pip_audit --cache-dir "$env:TEMP\arogya-audit"
.\.venv\Scripts\detect-secrets.exe scan --all-files --exclude-files '\.venv/|\.git/|__pycache__/|\.pytest_cache/'
git status --short
git diff --check
```

See [engineering and security report](docs/PHASE1_REPORT.md) for executed results,
including the blocked real-model check. Mocked passing tests are not evidence of
real model quality.

## Security boundaries and limitations

The sole token grants administrator access to every session. This is a local
admin prototype, with no end-user identity, per-user authorization, frontend
token distribution, production TLS, or multi-tenant isolation. Never send this
token to a future user/mobile frontend. Future browser participation needs
separate scoped credentials before exposure.

CORS is empty by default; only explicitly configured origins are allowed.
Requests are limited to 8 KiB and messages to 2,000 characters; each session
has 40 successful model turns. AI requests are serialized, time out, cap response
bytes and generation tokens, and use a 4,096-token context setting. History retains
at most 8 messages per session for 100 sessions in memory. Restart/eviction drops
history; validated facts and pending confirmation survive in SQLite.
In-memory history remains until closure, eviction, or process exit.
There is no retention scheduler or database encryption. Protect the local
database with OS account permissions and delete it when no longer needed.
No request bodies, model responses, or tokens are logged by application code;
start Uvicorn with access logging disabled as shown.

All SQL uses ORM parameter binding; LLM fields and types are untrusted and
validated. Role and required-field changes can only be made in trusted backend
configuration. Prompt injection can still influence generated wording or
plausible field values; model-generated text is not a security authority.
Review summaries carefully. Small models may misunderstand language, dates, or
instructions. Date validation rejects past dates; follow-up times are bounded
text and do not implement timezone or scheduling semantics. Appointment requests
are records, not bookings or clinical guidance. Do not collect real patient data
for this hackathon demonstration.

## Phase history and next scope

Phase 2 now adds the browser calling workflow, offline speech adapters, and React
interfaces; consult the Phase 2 report for test boundaries and local validation.
Phase 3 adds the current cross-platform profiles, offline Piper adapter,
portable validation tooling, and OS-specific setup guides. Real-device
acceptance remains pending as recorded in the Phase 3 report.

## Git review

The existing GitHub repository is used as-is; its visibility has not been changed.
No commit or push is performed automatically. Review the report and diff before
explicitly authorizing a commit, then authorize pushing. Suggested message:
`feat: build secure Arogya Caller AI backend`.
