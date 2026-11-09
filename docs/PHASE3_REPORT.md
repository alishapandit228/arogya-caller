# Phase 3 — cross-platform integration report

Date: November 10, 2026 (Asia/Kolkata). Target branch: main, existing private
alishapandit228/arogya-caller repository. Phases 1 and 2 are preserved.

## Delivered

One FastAPI/React application supports platform-specific local configuration:
Windows x64 defaults to Piper; macOS uses installed say, or optionally Piper;
Linux retains espeak for development. No second application, paid service,
telephone integration, Docker, queue service, public tunnel or cloud AI was added.

Explicit AI_PROFILE values: auto, windows16, macos8, portable.
Windows and Mac default to qwen2.5:3b; explicit OLLAMA_MODEL overrides the default.
Windows 7B and Mac 1.5B are documented opt-in alternatives, not automatic
performance decisions. No installed models are downloaded or switched by the
application. Existing explicitly configured model choices remain in effect.

TTS_ENGINE selects auto/piper/say/espeak. TTS_VOICE selects an installed say
or espeak voice. Piper's voice is selected by PIPER_MODEL_PATH and optional
PIPER_CONFIG_PATH. The maintained piper-tts 1.8.0 package has published Windows
AMD64 and macOS Intel/ARM64 wheels, verified from PyPI metadata; publication
of wheels does not establish successful execution on those machines.

The Piper adapter checks package and local model/config presence, invokes a
fixed Python worker with argument arrays and UTF-8 stdin, and validates bounded
mono PCM WAV output. Its private temporary output is deleted after success or
failure. No shell or user-selected executable is used. PiperVoice.load uses the
installed package's API, CPU provider and local paths; documented English
espeak-phonemized voices are enforced to avoid dynamic phonemizer downloads.
Optional package installation/download commands are separate from runtime.
Piper is GPL-licensed; its voice card must be reviewed for redistribution.

macOS say behavior remains available, now with configurable installed voice.
Missing executables/packages/weights fail clearly. Only controlled setup-error
messages reach API clients; arbitrary native error output remains hidden.

Whisper retains tiny.en, CPU/int8, two threads, beam 1, VAD, local_files_only.
Optional base.en uses an explicitly selected local path. Missing weights are
detected before a worker runs. The worker writes UTF-8 bytes explicitly, avoiding
Windows console/pipe encoding differences. Whisper/Piper resources are released
when each bounded worker exits. ONNX telemetry is disabled before inference.

The existing one-call and one-processing-operation limits, audio byte/duration
caps, bounded history, consent, confirmation, JSON validation, cancellation
commit guard, SQLite storage, cookie scopes and Origin checks remain active.
The frontend test backend launcher now chooses the correct .venv interpreter
on Windows/macOS/Linux and spawns argument arrays without shell interpolation.

## Files

- backend/app/core/profiles.py and config.py: explicit profile/default selection.
- backend/app/voice/audio.py: shared speech error/WAV/summary validation, moved
  from speech.py without changing its external imports.
- backend/app/voice/tts.py and piper_worker.py: platform-aware offline synthesis.
- backend/app/voice/speech.py, whisper_worker.py, manager.py: STT preflight,
  UTF-8 output, safe public setup errors, shared TTS adapter.
- backend/requirements-piper.txt: optional pinned Piper dependency.
- backend/scripts/check_local.py: read-only local prerequisites and Ollama model
  availability check, with no credential output or downloads.
- frontend/scripts/start-test-backend.mjs and playwright.config.js: portable
  browser-test process launch.
- backend/tests/test_platforms.py and existing voice test fixture: isolated
  platform/worker regression checks.
- .env.example, .gitignore, README, WINDOWS_SETUP.md, MACOS_SETUP.md and this report.

## Executed evidence — Linux cloud only

| Check | Actual result |
|---|---|
| Complete isolated backend suite | 103 passed, 6 opt-in real tests deselected |
| Frontend Vitest | 4 passed |
| Frontend production build | Passed |
| Chromium browser call flow | 1 passed using installed Chromium |
| Real FFmpeg decode/WAV normalization and duration limits | Passed in regression/browser tests |
| Explicit real local model/voice checks | 6 failed because local weights/Ollama/TTS prerequisites are unavailable |
| Read-only checker with Piper configured | Correctly failed for missing Whisper/Piper weights and unavailable Ollama; packages/FFmpeg detected |
| Piper package on Linux | Installed 1.8.0; real load/synthesize signatures and voice-download CLI checked, no voice inference |
| Bandit | No reported findings, four documented fixed-subprocess exclusions |
| pip-audit, including installed Piper/Whisper dependencies | No known vulnerabilities found |
| npm audit | 0 vulnerabilities |
| detect-secrets | 0 findings before final review |

Platform tests mock OS selection and subprocess output. They validate Windows
Piper argument boundaries (including spaces/metacharacters), model/config checks,
WAV output and temporary-file removal on success/failure; macOS say voice and
executable handling; invalid platform/engine; profile defaults/overrides;
Whisper CPU/int8/local-only arguments and UTF-8 output; Piper CPU API and
phonemizer restriction; safe subprocess timeout handling.

The original API/voice suite still covers authentication, recipient ownership,
invitations/expiry/reuse, secure cookies, WS Origin/expiry/malformed input,
initiation/accept/reject, consent/refusal, STT/LLM/TTS mocking, corrections,
confirmation, extraction, SQLite persistence, malformed/oversized audio,
concurrent-operation rejection, model timeouts, cancellation races and disconnects.

The browser test exercises actual UI, HTTP, WebSockets, MediaRecorder and FFmpeg;
STT/LLM/TTS content is explicitly mocked. Its non-Secure cookies are confined to
loopback test HTTP; normal LAN operation requires trusted HTTPS and Secure cookies.

Six explicitly enabled real checks failed: direct Ollama prompt; appointment and
general conversations; consent refusal; offline speech roundtrip; complete real
voice API/persistence flow. They stopped at missing cloud-local prerequisites;
later extraction/confirmation assertions in those checks did not execute.
The cloud cannot reach either laptop's localhost. The earlier environment policy
denied model downloads; no bypass, mirror or public exposure was attempted.

## Security review

No new HTTP or WebSocket privileges/endpoints were introduced. Admin Bearer
credentials remain on the administrator device; recipients use independent,
short-lived opaque cookies and per-call owner checks. Exact Origin and HTTPS
LAN validation, invite consumption/expiry, logout/revocation and token expiry
remain covered by regression tests. React renders model/recipient text as text.

New subprocess calls use a fixed trusted Python interpreter/script and separate
arguments, never shell=True. User text is stdin, not command syntax. Piper model
and config paths are trusted backend configuration, not request fields. The
browser test wrapper uses child_process.spawn with shell:false. Parent deadlines,
waveform limits and private temporary-directory cleanup remain enforced.

Secret, certificate, database/backup, installer, native library, audio, model,
cache and dependency directories/extensions are ignored. No credential values,
private keys, local SQLite files, model weights or executable binaries should
enter the reviewed commit. Runtime errors do not expose native stderr or paths;
only a small allowlisted set of setup messages is public. Prompt injection
still cannot assign roles or change required schemas, but model wording/facts
remain untrusted until validated and explicitly confirmed.

Scanners found no critical/high issue in the reviewed source/dependencies.
Their clean output is not proof of complete security. Four reviewed Bandit
exclusions cover the pre-existing fixed subprocess runner/validator imports and
calls; no user-controlled shell execution finding was suppressed.

## Windows and macOS validation status

**Windows ASUS 16 GB:** configuration, published wheel support and adapter
behavior verified by metadata/mocks on Linux. Actual Windows installation,
native synthesis, microphone/speaker, Wi-Fi firewall and trusted mobile HTTPS
are NOT verified.

**MacBook Air 8 GB:** say adapter behavior/selection and optional Piper are
covered by mocks. The user previously reported a successful direct 3B Ollama
prompt; no real complete FastAPI voice call, say/Piper output, microphone,
speaker, memory/latency or phone HTTPS has been independently verified here.

Before claiming hardware readiness, on EACH target machine:
1. Pull this reviewed main branch without overwriting local changes.
2. Follow that OS's setup guide; explicitly install weights and select profiles.
3. Run check_local.py until all prerequisites pass, then run the six real tests.
4. Use trusted LAN HTTPS on a personal mobile device with the receiving page open.
5. Demonstrate both roles, rejection, consent refusal/acceptance, silence and
   microphone permission recovery, ambiguity/corrections, explicit confirmation,
   final JSON and SQLite results surviving a backend restart.
6. End during inference; disconnect/reconnect; verify no late completion.
7. Measure latency and Task Manager/Activity Monitor RAM. Keep one call at a time.
   Only then explicitly try Windows 7B, Mac 1.5B or base.en and repeat validation.
8. Record OS, browser, package/model versions and actual pass/failure output.
   Never send admin tokens, CA keys, .env values or real patient data in reports.

## Known limitations and Git

English-only lightweight speech models; foreground receiving page; private LAN
development; one active call/operation; no public hosting, distributed limits,
encrypted SQLite, retention scheduler or production identity system. Invitations
are capabilities and must be shared privately. Interrupted calls require a new
call; credentials/registry reset on server restart. Short-lived model workers
favor predictable RAM over warm-model synthesis latency. Pipelines are not
benchmarked on either target, and mobile browser/codec differences remain a
real-device acceptance task. Failed real checks must not be relabeled passed.

The user authorized reviewed Phase 3 commit/push to existing private main.
Compare fetched remote history before committing; stop for unrelated changes;
never force-push. Publish only after eligible automated tests and security review
pass, keeping these external real-device blockers explicit. The final commit
hash and remote equality check are reported in the completion message.
