# Phase 1 engineering report

Date: November 9, 2026. Scope: backend text conversations only.

## GitHub transfer preparation

The user explicitly authorized creating a private repository, committing, and
pushing reviewed Phase 1 code with message:
feat: implement Arogya Caller Phase 1 backend.

Precommit checks rerun: 50 mocked tests passed, 4 real tests deselected.
Bandit reported no findings with the two documented subprocess exclusions;
pip-audit reported no known vulnerabilities. Credential scanning returned 0 findings. All 20 staged text files were reviewed
and confirmed to match the scanned working files; no database/model/binary or
credential artifacts were staged. Ignore checks passed for
environment files, virtual environment, databases/SQLite sidecars, private
keys/credential directories, caches, and model files.

The existing origin is alishapandit228/arogya-caller. The user confirmed it
was changed to Private and verified its visibility. The cloud's anonymous
repository-page request now returns HTTP 404 while authenticated Git fetch
succeeds, consistent with that confirmation. GitHub API administration remains
blocked by the cloud policy; no policy bypass or duplicate repository was used.

The reviewed backend commit is 055b2ee2863de5922e36dffba13ea3d08f901964.
Before pushing, remote main was fetched and verified to be its direct ancestor
(the original commit 0ecb48ea561174e4067bb064f2829bf4bfe8c120);
there were no unrelated remote changes or conflicts. The local worktree was
clean. This documentation update records the removed visibility blocker.
Publishing uses a normal fast-forward push to main, without force or history
rewriting. The same 50 mocked tests and security checks were rerun before
publishing; real AI backend validation remains pending on the MacBook.

Remaining risks are unchanged: real AI backend validation is pending on the
MacBook; small-model errors/prompt influence, single-admin access, local
unencrypted database, in-memory transcript retention, and single-worker limits.
No production-security or successful real backend AI validation claim is made.
See MACOS_REAL_AI_VALIDATION.md for exact local commands.

The sections below preserve the development and validation record; references
to earlier uncommitted state describe those earlier checks.

## Current macOS follow-up (supersedes earlier test totals below)

**User-reported Mac result:** macOS / zsh, Ollama 0.40.13, qwen2.5:3b
successfully generated an introduction and consent question through ollama run.
This is direct model evidence supplied by the user, not an independently
observed successful FastAPI flow. The version string is recorded as supplied.

**Observed cloud results:** the executor is Linux. A request to
http://localhost:11434/api/tags failed with connection refused. The cloud
localhost is not the Mac's localhost; no public exposure, tunnel, network-policy
bypass, or new download was attempted.

Changes:
- .env.example now selects OLLAMA_MODEL=qwen2.5:3b.
- Existing Settings environment override is retained; the lightweight 1.5B
  fallback remains for machines that do not configure OLLAMA_MODEL.
- Added two mocked tests proving environment override and selected-model
  forwarding to the Ollama HTTP client.
- Real integration tests now report the configured model in missing-model errors.
- Added backend/scripts/validate_local.py for real TCP FastAPI conversations,
  direct model probing, structured results, direct SQLite row comparison, and
  retrieval after stopping and restarting its own backend process.
- Added docs/MACOS_REAL_AI_VALIDATION.md with exact zsh setup, exports,
  backend startup, validation, and security commands.
- No core application behavior, public binding, paid service, or Phase 2 added.

Executed in this cloud environment with OLLAMA_MODEL=qwen2.5:3b and
OLLAMA_URL=http://localhost:11434:
- Automated mocked suite: **50 passed** (original 48 plus 2 model selection
  checks), 4 real tests deselected.
- Explicit real integration suite: **4 failed**, 50 mocked tests deselected.
  Direct model probe failed on connection refused. Both role flows and refusal
  received 503 at their first model-dependent reply. Real extraction,
  confirmation, and persistence assertions were not reached.
- Real TCP validation runner: **failed at the Ollama preflight**, connection
  refused; backend launch and conversation/restart branches were not executed.
- Bandit, application plus validation script: **0 reported findings**, with
  **2 narrowly documented low-severity subprocess exclusions** (B404/B603).
  Manual review: it launches sys.executable with a fixed Uvicorn module and
  arguments, no shell or user-supplied command, loopback only; cleanup stops only
  its own child. Application scanning itself has no exclusions.
- pip-audit: **no known vulnerabilities found**.
- detect-secrets: **0 findings**.
- git diff --check: passed.
- Starlette's HTTPX TestClient deprecation warning remains.

No Mac commands have been executed by this remote agent. The real runner and
four real tests must still be executed on the Mac with the updated working
files installed. They are prepared checks, not claimed passing evidence.
The 50 passing mocked tests verify deterministic role-specific field rejection,
date/time validation, confirmation/state controls, and persistence under test
conditions; they do not establish real-model semantic accuracy.

Follow [macOS real AI validation](MACOS_REAL_AI_VALIDATION.md).
Successful validation requires a PASS from the HTTP runner and passing real
tests, plus review of the printed synthetic questions and structured fields.
If the model gives invalid JSON, extracts wrong facts, misses a field, or times
out, preserve that failure for diagnosis. The backend remains unverified against
the user's reported Ollama version and 3B model until that evidence is supplied.

No commit or push was made. Pause for user confirmation after successful real
validation; Phase 2 remains out of scope. Older Windows instructions are retained
only as optional documentation and do not describe the user's current OS.

## Development

Implemented all eight requested endpoint paths, including GET and POST /sessions:
health, roles, creation, reply, session retrieval, confirmed result retrieval,
paginated listing, cancellation. Roles and session logic are reusable through
trusted Python configuration. Optional name, contact reason/follow-up, and
appointment purpose/date/time are supported.

Files prepared:
- .env.example, .gitignore, README.md
- backend/requirements.txt and requirements-dev.txt
- backend/pytest.ini
- backend/app/__init__.py, main.py
- backend/app/agents/roles.py
- backend/app/core/config.py
- backend/app/models/session.py
- backend/app/schemas/conversation.py
- backend/app/services/engine.py and ollama.py
- backend/tests/test_api.py and test_integration.py
- docs/PHASE1_REPORT.md

SQLite tables are created at startup. Actual HTTP and tests verified
create/read/update and persistence across app recreation. No database or token
is included in the review files. Histories remain bounded in process memory,
not in database rows.

Ollama HTTP integration is implemented with schema-constrained JSON,
bounded output/history, validation, timeout handling, and generic error handling.
**Real model operation has not been verified.** Ollama is absent on this cloud
machine; its official download received network-policy HTTP 403. The real
integration test was explicitly executed and failed with the expected API 503
when connecting to the unavailable local service. No simulated answer is used
as an application fallback.

## Executed verification

| Check | Result |
|---|---|
| Python / Git | Python 3.12.14 / Git 2.52.0 |
| Mocked suite: pytest -q -m "not integration" | 48 passed, 0 failed; 1 real test deselected |
| Real suite: RUN_OLLAMA_INTEGRATION=1 pytest -q -m integration | 1 failed, 39 deselected at execution time; Ollama unavailable |
| Real Uvicorn HTTP smoke | Passed: health, 401, authenticated SQLite create/read/cancel |
| Bandit 1.9.4, application source | 0 findings; no skipped checks |
| pip-audit 2.10.1, installed virtual environment | Final: no known vulnerabilities found |
| detect-secrets 1.5.0, all nonignored source files | 0 findings |
| git diff --check | Passed |
| Gitleaks | Not installed; release API request denied HTTP 403; detect-secrets used instead |

The mocked suite covers valid/invalid roles; all protected endpoints with
missing, invalid, and wrong-scheme authentication; consent acceptance/refusal;
no collection before consent; required data extraction and missing fields;
date/time validation; correction and confirmation; cancellation; terminal
transitions; persistent results; model errors/invalid JSON/timeout/invalid
types; body/message limits; prompt attempts to modify role or authorize
consent/confirmation; existing result access without authorization; CORS,
input-error privacy, pagination limits, SQL-looking input, configuration safety,
and the conversation turn budget.

One dependency deprecation warning is emitted by Starlette's HTTPX TestClient
adapter. Tests executed successfully. It does not affect the production Ollama
HTTPX client. No warning was suppressed.

## Security review

| Area | Controls and findings |
|---|---|
| SQL injection / database operations | SQLAlchemy parameter binding; UUID path validation; no concatenated user SQL |
| Authentication / authorization / object access | All endpoints except public health require the single admin token, including roles and existing results |
| Least privilege boundary | One local administrator only; no ordinary-user access path; per-user identity is not implemented |
| Prompt injection | Trusted frozen role/required fields; unknown output fields rejected; explicit consent/confirmation gate; terminal transitions controlled by Python |
| Untrusted LLM facts | Schema/type/length validation and final human confirmation; semantic correctness cannot be guaranteed |
| Malicious input / resource limits | 8 KiB request bodies, 2,000-character messages, bounded history/output, 40-turn budget, one AI call at a time |
| Secrets / environment | No fixed production token; startup rejects short/missing tokens; local-only Ollama URL; example has no value |
| Disclosure / logging | Generic HTTP/model/validation errors, no input echo or application body logs; no-store headers; access logging disabled in startup instructions |
| CORS | Default deny; explicit origin validation, no wildcard |
| Sessions | Enumerated valid transitions; completed/cancelled/failed immutable; results unavailable until completion |
| Sensitive data | No transcript/audio persistence; cancellation clears fields; database unencrypted and has no automated retention |
| Dependency vulnerabilities | Initial audit found 12 advisory entries in bundled pip 25.0.1 (some duplicate identifiers); upgraded to pip 26.3 and reran successfully |
| Git hygiene | Environment, venv, SQLite, logs, model artifacts, and caches excluded; final secret scan clean |

Review corrections included requiring explicit text as well as model consent/
confirmation intent, invalidating pending confirmation after rejected corrections,
and ensuring the model's structured unknown fields fail closed. No critical or
high-severity application finding was identified by this review or Bandit.
These checks do not establish that the application is vulnerability-free.

Remaining risks: small-model hallucination and prompt-influenced wording,
unencrypted local database, process-memory history retention until eviction/
termination, single administrator with access to every session, no distributed
rate limiting, and single-worker concurrency constraints. Keep both servers on
localhost and use synthetic data. Raw model text must be escaped by any future UI.
This is not a medical advice or production patient-data system.

## GitHub status and approval boundary

Existing repository: alishapandit228/arogya-caller. Its visibility was not changed.
README.md modified; 19 new files prepared (20 review files total), including the Windows/macOS guides and real HTTP validation runner.
No files staged, no commit created, no push made, no new repository created.
Virtual environment and runtime outputs are ignored.
Secret scan found no candidate secrets in the prepared source set.

Suggested commit: feat: build secure Arogya Caller AI backend

The source is available for review, but a fully validated Phase 1 / readiness to
push claim is withheld until the real Ollama integration passes. Explicit user
approval is required before committing and before pushing. If a new repository
is ever authorized, use private visibility by default.

## Required next validation

On Windows, follow README.md to install Ollama, pull qwen2.5:1.5b, start its local
server, and run the opt-in real integration command. On this cloud environment,
the equivalent requires access to ollama.com for the official runtime,
registry.ollama.ai for the model, and any actual redirected model CDN destinations;
the existing policy rejected the runtime download. No network policy was broadened.

Then exercise both roles manually with ambiguous answers and corrections; inspect
real generated questions and summaries. Model quality may require prompt
adjustments after those observations. Do not proceed to Phase 2 on the strength
of mocked tests alone.

Phase 2 and Phase 3 remain planned; no voice, calling, React, webhook delivery,
or production identity infrastructure was implemented.
