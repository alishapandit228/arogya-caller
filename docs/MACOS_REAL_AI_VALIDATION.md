# macOS / zsh: Phase 1 real AI validation

The user reports Ollama 0.40.13 and a successful qwen2.5:3b introduction/consent
prompt on the Mac. That verifies a direct model interaction, not the FastAPI
conversation flow. Codex is attached to a Linux cloud machine; its localhost
does not reach the Mac. All commands below run in the Mac's Terminal, from the
local arogya-caller repository root, with these updated working files present.
No Git commit/push is needed for validation.

## Local setup and model selection

```zsh
python3.12 --version
# Create a Mac-specific venv; do not copy the Linux .venv to the Mac.
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt

export OLLAMA_MODEL='qwen2.5:3b'
export OLLAMA_URL='http://localhost:11434'
export TRUSTED_ORIGINS='[]'
export ADMIN_API_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL='sqlite:///./arogya.db'

ollama --version
ollama list
curl --fail --show-error http://localhost:11434/api/version
curl --fail --show-error http://localhost:11434/api/tags
```

If python3.12 is unavailable, install Python 3.12 for macOS from
https://www.python.org/downloads/macos/ before creating the environment.
If Ollama is stopped, run `open -a Ollama` or use `ollama serve` in a second
Terminal tab. Keep its default loopback binding. Do not start another server
if the first already owns port 11434. The installed 3B model need not be
downloaded again. If absent, the official command is `ollama pull qwen2.5:3b`.
The backend keeps 1.5B as its low-memory default, but OLLAMA_MODEL overrides it;
.env.example now shows the user's selected 3B configuration. Exported variables
override a local .env. The tests and validation runner honor OLLAMA_MODEL.

## Actual HTTP conversation and database verification

```zsh
.venv/bin/python backend/scripts/validate_local.py
```

This command performs a real Ollama API prompt, starts its own loopback Uvicorn
process on a temporary port, and sends authenticated HTTP requests for both
roles. It checks consent, required fields, confirmation, role field boundaries,
appointment date/time normalization, and structured result JSON. It compares
results to SQLite rows, restarts its backend process, and retrieves identical
results again. It prints the synthetic conversation responses for inspection.

No LLM call is mocked. Failures exit nonzero; a PASS is printed only after all
checks complete. Missing model/service fails before starting the backend.
The runner uses its own temporary database and random token, never prints
the token, stops only the process it started, and deletes its temporary data.
Existing application sessions/database are untouched.

Review the printed generated questions and extracted facts for correctness.
A successful direct introduction alone does not validate extraction or JSON
schema support in /api/chat. Do not suppress a failure or replace it with canned
responses. Share synthetic failure output for diagnosis.

## Automated tests and security checks

Run each command separately and stop to inspect any nonzero exit:

```zsh
(cd backend && ../.venv/bin/python -m pytest -q -m 'not integration')
(cd backend && RUN_OLLAMA_INTEGRATION=1 ../.venv/bin/python -m pytest -q -m integration)
.venv/bin/python -m bandit -r backend/app backend/scripts
.venv/bin/python -m pip_audit --cache-dir "${TMPDIR:-/tmp}/arogya-audit"
.venv/bin/detect-secrets scan --all-files --exclude-files '\.venv/|\.git/|__pycache__/|\.pytest_cache/'
git diff --check
git status --short
```

There are 50 mocked tests (the original 48 plus two model-selection tests) and
four opt-in real tests: direct model prompt, both role flows with app recreation
and SQLite persistence, and consent refusal. Deterministic invalid-date/time
and cross-role output rejection are exercised by the mocked tests; do not
describe those as observed real-model validation of malicious output.

A small-model semantic failure or timeout is unresolved until diagnosed.
Use one request/model at a time on limited RAM. The backend timeout is 90 seconds;
the script's client allows 100 seconds for a backend response.

## Start the normal backend for manual use

The runner above starts and cleans up its own server. To run the normal
persistent development server instead, use the same exported variables:

```zsh
.venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

This creates/uses arogya.db in the repository root. Keep the admin token local;
do not put it in browser code or paste it into chat. Do not publicly expose the
backend or Ollama, set up tunnels, or change network security policies.

Return the validation runner PASS/failure and test summaries, plus any synthetic
questions that look wrong. Local Mac results cannot be independently claimed by
the remote executor until supplied. Then pause for user confirmation; Phase 2,
committing, and pushing remain outside this task.
