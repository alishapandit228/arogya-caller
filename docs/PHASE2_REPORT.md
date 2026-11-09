# Phase 2 engineering and security report

Scope: Phase 2 only. Phase 3 is not implemented.

## Outcome and evidence boundary

Implemented a real browser-to-backend calling workflow with offline speech
adapters. Phase 1 endpoints and state/validation rules remain in use. The cloud
has verified mocked API/voice behavior, a real FFmpeg decoder, and a Chromium
UI/HTTP/WebSocket/recording flow with explicitly mocked STT/LLM/TTS.

**Real end-to-end voice inference and physical Mac/mobile audio are not
verified.** The user previously reported a successful direct qwen2.5:3b prompt
on the Mac. That is not a successful backend voice test. The cloud has no local
Ollama or macOS say/espeak, and its policy blocks the official Whisper model
download. Six opt-in real checks were executed and failed at these missing
prerequisites; they were not described as passing.

## Features and implementation

- React + Vite + Tailwind administrator dashboard: secure sign-in, role and
  connected-recipient selection, private enrollment link, initiate/end call,
  live status, persistent session history, and confirmed JSON results.
- Responsive receiver: one-use enrollment, incoming call accept/reject,
  consent/decline, microphone permission/error handling, listening/processing/
  playback states, transcription display, confirmation, end call, reconnect.
- FastAPI WebSocket signaling sends authorized state snapshots about once
  per second. It does not stream audio, accept arbitrary commands, or rely on
  peer-to-peer WebRTC/STUN/TURN. There is no background call delivery.
- Browser MediaRecorder uploads bounded WebM/MP4/WAV. FFmpeg validates/decodes;
  faster-whisper transcribes in a CPU/int8 subprocess. The existing AI engine
  extracts/validates fields and enforces consent, corrections, and confirmation.
- Offline macOS say (system English voice) synthesizes WAV via FFmpeg; optional
  Linux espeak adapter. Confirmation summaries use human-readable spoken labels
  while preserving structured JSON in text/results.
- Call metadata added in a separate SQLite table. Confirmed Phase 1 results
  persist. Interrupted calls are marked failed at restart; credentials and
  connections must be re-established.
- One active call and one voice computation at a time for an 8 GB target.
  Whisper workers exit before the LLM request to release their RAM.

Changed backend: main.py (internal reply callback/commit guard, audio body cap,
voice registration/recovery, punctuation normalization for spoken consent);
services/ollama.py (elapsed-budget checks in addition to read timeout);
core/config.py (voice settings and HTTPS LAN origins); new voice/models.py,
manager.py, routes.py, speech.py, whisper_worker.py; requirements-voice.txt;
new isolated/browser/real voice tests.

Added frontend: package.json/package-lock.json, Vite configuration, React
dashboard/receiver, API/signaling helper, Tailwind styles, Vitest tests,
Playwright browser test and test-server configuration.

Updated .gitignore, .env.example and README; added PHASE2_SETUP.md and this
report. Phase 1 report is retained as historical evidence.

## Interfaces

All browser actions use same-origin /voice through the HTTPS Vite proxy.
Mutations require an exact trusted Origin; cookies are HttpOnly, SameSite=Strict,
Secure by default. The Phase 1 Bearer-protected API remains separate.

| Method/interface | Path | Scope |
|---|---|---|
| POST | /voice/admin/login, /voice/admin/logout | Exchange/revoke admin session |
| GET | /voice/admin/state, /voice/admin/roles | Admin state/configuration |
| GET | /voice/admin/history | Admin session history (latest 100) |
| GET | /voice/admin/sessions/{id}/result | Admin confirmed result |
| POST | /voice/admin/recipients | Admin creates 5-minute single-use invitation |
| POST | /voice/join | Redeem invitation for 1-hour scoped receiver cookie |
| GET | /voice/me | Receiver's identity and own calls only |
| POST | /voice/admin/calls | Admin rings connected recipient with selected role |
| POST | /voice/admin/calls/{id}/end | Admin ends call |
| POST | /voice/calls/{id}/action | Owner accepts/rejects/ends/consents/confirms/refuses |
| POST | /voice/calls/{id}/audio | Owner uploads one audio turn |
| GET | /voice/calls/{id}/speech | Owner retrieves current synthesized WAV |
| WebSocket | /voice/ws/admin, /voice/ws/receiver | Cookie and Origin checked on handshake; expiry checked each tick |

Action JSON: {"action":"accept"} (or reject/end/consent/confirm/refuse).
Audio body is binary with its actual MediaRecorder Content-Type.
Signaling clients may send only {"type":"ping"}; other/malformed input closes
the socket. Tokens never appear in WebSocket query strings.

Calls: ringing → accepted → active → completed. Rejection, cancellation, or
failure may close unfinished calls. No session or agent speech is generated
while merely ringing. A lost receiver connection fails the current call;
automatic reconnection restores availability for a new call.

## Executed validation

| Check | Result |
|---|---|
| Existing Phase 1 + new isolated backend tests | 84 passed, 6 opt-in real checks deselected |
| Frontend Vitest | 4 passed |
| Frontend production build | Passed |
| Chromium browser call flow | 1 passed; real HTTP/WebSockets/MediaRecorder/FFmpeg, mocked inference |
| Actual FFmpeg WAV/WebM decode, malformed data, duration cap and finite WAV headers | Passed in isolated suite; STT worker mocked there |
| Explicit real Ollama + offline voice tests | 6 failed due missing cloud prerequisites; later conversation assertions unrun |
| Bandit app + local validator | No reported findings; narrowly documented fixed-subprocess exclusions |
| pip-audit, full Python environment including voice dependencies | No known vulnerabilities found |
| npm audit, including development dependencies | 0 vulnerabilities reported |
| Credential scan and staged artifact review | 0 findings; 27 reviewed text files, no keys/models/databases/runtime files |

Tests cover dashboard authentication; secure cookie flags/logout; recipient
connection; one-use and expired invites; initiation/offline recipient/invalid
role; acceptance/rejection/end; unauthorized call/audio/result access; missing
and expired WS credentials; malicious Origin; malformed WS/JSON; disconnect;
concurrent processor rejection; invalid/oversized/overlength audio; speech and
model failure; mocked transcription/generation/synthesis; consent including ASR
punctuation; role field rejection; explicit confirmation; cancellation during
model computation; completion; and SQLite results across app recreation.

The Chromium download endpoint was blocked. An already installed
/usr/bin/chromium was used normally, without bypassing destination policy.
An initial browser-test failure was traced to a test-only random token being
regenerated in the worker; this was fixed and the test rerun successfully.
Browser handshake-denial expiry handling was also covered with a unit test.
A modularization import error was caught and corrected by the backend tests.
No assertions were disabled to obtain a passing result.

The real offline adapter tests require say/espeak plus local Whisper weights.
The real voice API test additionally requires Ollama. They use synthesized
synthetic user turns, not physical hardware. The cloud's unavailable services
prevent a claim of speech accuracy, real-model JSON compatibility, device
echo cancellation, or trusted mobile HTTPS operation.

## Security review and remaining risks

- Admin and receiver opaque tokens are cryptographically random; only hashes
  are stored in memory. Cookies expire in one hour. Invitations expire in five
  minutes and are consumed atomically. Receiver credentials never authorize
  admin routes or the Phase 1 API.
- Per-call ownership checks apply to every receiver action/audio retrieval.
  Session UUIDs do not grant access. Exact Origin checks protect state changes
  and WS handshakes; non-loopback HTTP browser origins are rejected. Vite
  refuses LAN binding without TLS or with an incomplete certificate/key pair.
- Browser code uses React text rendering; no raw HTML rendering or storage of
  tokens in localStorage/sessionStorage. Invitations use fragments and are
  removed from the receiver address immediately.
- End/disconnect is serialized with the final session commit; a model-failure
  cancellation race also clears partial collected data. Consent and confirmation
  phrases are checked separately. Model output
  cannot complete a call after cancellation. Phase 1 consent/schema/state
  controls remain deterministic. Prompt injection can still influence wording
  or plausible extracted facts; final human review remains necessary.
- 2 MB encoded audio, 20 seconds decoded audio, 2,000 transcript characters,
  bounded generation/history, 60-second ringing timeout, and 15-minute idle
  call timeout. Browser capture stops by 19 seconds. One processing operation
  at a time; invitation/login/action/WS rate limits and recipient caps.
- FFmpeg reads stdin with a pipe-only protocol allowlist and stops on decode
  errors. No user-selected command, path, executable, or shell evaluation.
  Decoder/Whisper/TTS subprocesses have deadlines. Ollama checks elapsed time
  between chunks as well as a 90-second per-read timeout; an in-progress read
  can finish after the elapsed deadline before the failure is observed. Bandit subprocess exclusions
  document fixed local executable/module invocations; they do not suppress
  findings from user-controlled shell execution.
- Raw uploads are not saved. Say requires a private temporary generated-audio
  file, removed after conversion. Only the latest synthesized response is kept
  temporarily in memory; end clears it. SQLite retains structured data/metadata.
  Logs omit request bodies, transcript content, and credential values.
- TLS development certificates/keys, environment files, model weights, audio,
  databases, dependency folders, caches, and browser output are ignored.

Limitations: trusted private Wi-Fi only; no production deployment/identity,
distributed rate limiter, encrypted database, retention scheduler, account
recovery, background calls, multiple receiver tabs, or concurrent calls.
Invitations are capabilities: a stolen unused link can enroll its holder.
Receiver sessions cannot be refreshed indefinitely; re-enroll after expiry.
Disconnected calls are not resumed. The dashboard shows the latest 100 sessions.
Transient credentials/recipient registry require re-enrollment on restart.
The in-memory recipient registry caps at 50 enrollments per process lifetime.
No clinical or real patient-data usage should be inferred.

A final TTS failure after successful confirmation retains confirmed SQLite
results; playback can fail independently of data completion. Speech errors,
silence, and small-model misunderstandings require retry or a new call. System
FFmpeg/TTS software must remain patched through the operating system/package
manager. Scans do not prove the application vulnerability-free.

## Local acceptance steps and Git

Follow PHASE2_SETUP.md for exact Mac/phone instructions: install the official
tiny.en weights; trusted mkcert HTTPS on Wi-Fi; leave Ollama/backend bound to
loopback; run the real opt-in tests; then conduct real calls with microphone and
speaker, including rejection, consent refusal, ambiguous date/time correction,
end during processing, disconnect, and dashboard JSON review.

The user approved reviewed Phase 2 commits and a normal push to the existing
private alishapandit228/arogya-caller repository. Target branch: main.
Before committing, review staged files, scan for credentials and local artifacts,
rerun affected tests/security checks, and compare fetched remote history.
Never force-push or overwrite unrelated remote work. Final commit and remote
verification are reported after the push.
