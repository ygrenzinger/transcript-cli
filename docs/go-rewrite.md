# Go Reimplementation Tracker

Purpose: reimplement the current Python `video-to-srt` tool in Go while preserving the behavior required by `openspec/` and keeping the Python implementation available as the reference.

## Interview Decisions

- Scope: feature parity with the current Python tool before adding new behavior.
- Location: create a new `go/` implementation directory.
- Existing CLI: keep the current Python CLI unchanged during the rewrite.
- Task tracker: maintain this file at `docs/go-rewrite.md`.
- Test bar: unit tests for each implementation step.
- External tools: use `ffmpeg` as a subprocess for media extraction/conversion; Go wrappers are acceptable.
- Go version: latest stable Go.
- Cloud APIs: prefer direct HTTP first; use SDKs only where direct HTTP is impractical.
- CLI compatibility: preserve the Python flags, artifact naming, stderr progress format, and exit behavior.
- Sherpa Parakeet: keep a Go provider boundary and use the most pragmatic shell/tool/library integration available.
- Fixtures: shared fixtures/golden files are allowed for deterministic parity checks.
- Post-parity: keep Python as the reference implementation.

## OpenSpec Scope

- `openspec/specs/audio-extraction/spec.md`: video input acceptance, MP3 output, explicit no-audio failure, idempotent re-extraction.
- `openspec/specs/audio-to-srt-transcription/spec.md`: provider contract, retries, provider/model selection, discoverability, language hints, provider configuration, Voxtral/Grok/Vertex/Sherpa behavior.
- `openspec/specs/pipeline-orchestrator/spec.md`: end-to-end pipeline, stage isolation, improved-output validation gate, progress reporting, failure handling, intermediate artifact lifecycle, single-command UX.
- `openspec/specs/srt-validation/spec.md`: parseability, sequential indices, exact timestamp format, monotonic/non-overlap, UTF-8/LF encoding, non-empty cue text, pure validation.
- `openspec/specs/subtitle-improvement/spec.md`: optional improvement, invalid cue filtering, duration/CPS/line limits, split boundaries, speaker handling, gaps, idempotence, re-indexing.

## Current Python Reference

- CLI entry point: `python/transcribe.py` via `video-to-srt`.
- Internal modules: `extract_audio.py`, `providers.py`, `srt.py`, `improve_subtitles.py`, `validate_srt.py`.
- Providers: `voxtral`, `grok`, `vertex-gemini`, `sherpa-parakeet`.
- Output naming: `<video>.<provider>.raw.srt` and, when requested, `<video>.<provider>.improved.srt`.
- Audio lifecycle: extracted `<video>.mp3` is removed after successful raw SRT creation and retained when transcription fails.
- Progress format: lines on stderr beginning with `PROGRESS`, including `stage`, `name`, `status`, and contextual fields.

## How To Use This File

- Mark a task done by changing `[ ]` to `[x]` only after its acceptance criteria pass.
- After each completed task, update that task's `Context compact` line with the minimum information needed to resume later.
- Keep each task small enough to complete and verify independently.
- Do not remove completed tasks; this file is the continuity record.

## Tasks

### 1. Bootstrap Go Workspace

- [x] Create `go/` with `go.mod`, an initial package layout, and a minimal command package for the future `video-to-srt` binary.
- Acceptance criteria: `go test ./...` runs successfully from `go/`; no Python files are modified.
- Context compact: Added `go/` module, `cmd/video-to-srt`, and internal packages; `go test ./...` passes.

### 2. Define Core Domain Types

- [x] Add Go types for subtitle cues, provider metadata, provider errors, and pipeline options/results.
- Acceptance criteria: types represent cue index, start/end milliseconds, text, optional speaker, provider name, supported models, default model, required env vars, language hint, and output paths.
- Context compact: Added cue, provider metadata/error, registry, retry, and pipeline option/dependency types.

### 3. Port SRT Formatting

- [x] Implement timestamp formatting and SRT writing equivalent to `python/srt.py`.
- Acceptance criteria: unit tests cover millisecond-to-timestamp conversion, cue re-indexing on write, speaker prefix formatting, UTF-8/LF output, and empty cue output.
- Context compact: `internal/srt` formats timestamps, reindexes on write, handles speakers, LF/UTF-8 output, and empty output.

### 4. Port SRT Parsing

- [x] Implement SRT byte reading and parsing equivalent to `python/srt.py`.
- Acceptance criteria: unit tests cover BOM rejection, CRLF rejection, invalid UTF-8 rejection, missing final newline, malformed cue blocks, invalid timing lines, empty cue text, speaker-prefix extraction, and valid parsing.
- Context compact: `internal/srt` rejects BOM/CRLF/invalid UTF-8/malformed input and extracts speaker prefixes.

### 5. Port SRT Validation

- [x] Implement pure SRT validation equivalent to `python/validate_srt.py` and `openspec/specs/srt-validation/spec.md`.
- Acceptance criteria: unit tests cover sequential indices, positive duration, non-overlap, parse failures, and no file mutation.
- Context compact: `internal/srt.ValidateFile` checks parseability, sequential indices, positive durations, and non-overlap without mutation.

### 6. Add Shared Test Fixtures

- [x] Add deterministic SRT fixtures under a shared `testdata/` location usable by Go and Python.
- Acceptance criteria: fixtures include valid SRT, malformed SRT, overlapping cues, invalid durations, long cues, speaker-labeled cues, and CRLF/BOM cases where useful.
- Context compact: Added shared `testdata/` SRT fixtures for valid, malformed, overlap, invalid duration, long cue, speaker labels, CRLF, and BOM.

### 7. Port Subtitle Improvement Constants And Text Helpers

- [x] Port constants and helper behavior from `python/improve_subtitles.py`: displayed length, wrapping, best line break, word splitting, and split-point selection.
- Acceptance criteria: unit tests cover 42-character line wrapping, two-line limit behavior, punctuation-preferred wrapping, clause-boundary wrapping, and whitespace normalization.
- Context compact: `internal/improve` ports constants, displayed length, wrapping, punctuation/clause/word split helpers, and whitespace normalization.

### 8. Port Subtitle Splitting Rules

- [x] Port long-cue splitting, duration limits, character limits, CPS enforcement, and preferred boundary selection.
- Acceptance criteria: unit tests cover cues over 7 seconds, text over 84 characters, high CPS cues, sentence punctuation boundaries, clause punctuation boundaries, and word-boundary fallback.
- Context compact: `internal/improve` splits long/high-CPS/over-84-char cues and enforces max duration in tests.

### 9. Port Speaker And Gap Improvement Rules

- [x] Port embedded speaker-change splitting, multi-speaker labeling, single-speaker label suppression, and 80 ms inter-cue gap enforcement.
- Acceptance criteria: unit tests cover mid-cue speaker markers, multi-speaker prefix output, single-speaker no-prefix output, touching cues, overlapping cues, and minimum-duration preservation.
- Context compact: `internal/improve` handles embedded speaker markers, multi-speaker prefixes, single-speaker suppression, and gap adjustment.

### 10. Finish Subtitle Improvement Pipeline

- [x] Compose parsing, invalid cue filtering, splitting, CPS extension, gap enforcement, wrapping, re-indexing, writing, and validation.
- Acceptance criteria: unit tests cover idempotence, zero/negative-duration raw cue removal, raw input unchanged, improved output validation, and byte-stable second pass.
- Context compact: `ImproveFile` composes parse/improve/atomic write/validate; tests cover idempotence and raw input preservation.

### 11. Implement Audio Extraction With ffmpeg

- [x] Implement video-to-MP3 extraction using the `ffmpeg` executable.
- Acceptance criteria: unit tests use a fake command runner to cover missing input, existing non-empty MP3 cache hit, no-audio/ffmpeg failure propagation, atomic output behavior, and default `<video>.mp3` path.
- Context compact: `internal/audio` uses `ffmpeg` through a runner interface with cache hit, default path, atomic temp output, and failure cleanup tests.

### 12. Implement Provider Registry And Model Resolution

- [x] Implement provider registration, lookup, model resolution, provider discoverability JSON, and required environment validation.
- Acceptance criteria: unit tests cover all provider names, default models, unsupported provider errors listing available providers, unsupported model errors listing available models, and missing env var messages.
- Context compact: `internal/provider.Registry` registers all providers, resolves models, validates env vars, and emits JSON discovery.

### 13. Implement Retry Policy

- [x] Implement provider retry wrapper with 1s, 2s, and 4s default delays plus `Retry-After` override for HTTP 429.
- Acceptance criteria: unit tests use fake clocks/sleepers and fake provider errors to cover transient success, retry exhaustion, non-transient no-retry, HTTP 5xx retry, HTTP 429 retry, numeric `Retry-After`, and HTTP-date `Retry-After`.
- Context compact: `TranscribeWithRetries` covers transient errors, HTTP 5xx/429, numeric/date Retry-After, exhaustion, and no-retry cases.

### 14. Implement Grok Provider

- [x] Implement `grok` transcription via direct HTTP.
- Acceptance criteria: unit tests use an HTTP test server to cover request method/path/headers, multipart audio upload, model and language fields, JSON segment parsing, word-level cue grouping, malformed JSON, HTTP error wrapping, empty-result failure, and atomic SRT write.
- Context compact: `GrokProvider` posts multipart direct HTTP, forwards model/language, parses segments/words, wraps HTTP/JSON errors, and atomically writes SRT.

### 15. Implement Voxtral Provider

- [x] Implement `voxtral` transcription with the most practical direct HTTP or SDK approach, while preserving provider boundary behavior.
- Acceptance criteria: unit tests cover env validation, default model `voxtral-mini-2602`, language forwarding, segment-to-cue conversion, text fallback, empty response failure, provider error wrapping, and atomic SRT write.
- Context compact: `VoxtralProvider` exposes Go metadata/model/env boundary and invokes the Python reference provider bridge for operational SDK behavior.

### 16. Implement Vertex Gemini Provider

- [x] Implement `vertex-gemini` transcription using Google ADC plus `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
- Acceptance criteria: unit tests isolate API calls behind a small client interface and cover default/pro model selection, language hint in prompt/config, JSON segment parsing, malformed response failure, empty response failure, invalid timestamps, non-positive durations, out-of-order segments, and atomic SRT write.
- Context compact: `VertexGeminiProvider` validates project/location, supports injectable Go client and response parsing, and falls back to Python reference bridge for ADC calls.

### 17. Implement Sherpa Parakeet Cache Management

- [x] Implement cache-root resolution, model archive download, safe extraction, required file validation, and cache reuse for `sherpa-parakeet`.
- Acceptance criteria: unit tests cover default cache root, env override, valid cache reuse, missing cache download, unsafe archive path rejection, missing required files, download failure, extraction failure, and replacement of invalid cache.
- Context compact: Sherpa cache root/env override, model dir validation, tar.bz2 safe extraction, cache reuse, and failure paths are implemented/tested.

### 18. Implement Sherpa Audio Preparation

- [x] Implement provider-internal audio preparation for sherpa-compatible mono 16 kHz PCM WAV using `ffmpeg` or an agreed wrapper.
- Acceptance criteria: unit tests use a fake command runner to cover MP3-to-WAV command construction, conversion failure, empty output failure, temp artifact cleanup, and no language-hint error.
- Context compact: `PrepareSherpaAudio` runs `ffmpeg -ac 1 -ar 16000 -acodec pcm_s16le` through a fakeable runner and cleans failed output.

### 19. Implement Sherpa Recognition Boundary

- [x] Implement the `sherpa-parakeet` runtime boundary using the selected pragmatic shell/tool/library integration.
- Acceptance criteria: unit tests cover runtime candidate order, `SHERPA_ONNX_PROVIDER` override, CPU fallback, thread env parsing, segment-to-cue conversion, token/timestamp-to-cue conversion, text fallback, empty result failure, invalid timestamps, and out-of-order timestamps.
- Context compact: Runtime candidate order/thread parsing and segment/token/text conversion are implemented; operational runtime defaults to Python reference bridge.

### 20. Implement Atomic SRT Writes

- [x] Centralize atomic SRT writes used by all providers and improvement output.
- Acceptance criteria: unit tests cover parent directory creation, successful temp-file replacement, temp cleanup on write failure, and no partial output on error.
- Context compact: `internal/srt.AtomicWriteFile` centralizes parent creation, temp writes, replacement, and cleanup.

### 21. Implement Pipeline Orchestrator

- [x] Implement the Go pipeline that wires provider validation, audio extraction, transcription with retries, audio cleanup, optional subtitle improvement, and improved-output validation.
- Acceptance criteria: unit tests with fakes cover raw-only happy path, improved happy path, stage call order, failure stops subsequent stages, raw SRT preserved, improved SRT only when requested, audio removed only after successful raw SRT, and audio retained on transcription failure.
- Context compact: `internal/pipeline.Run` wires validation, extraction, retry transcription, cleanup, optional improvement, validation, and artifact naming.

### 22. Implement Progress Reporting

- [x] Emit Python-compatible progress lines on stderr for stage start, done, and fail.
- Acceptance criteria: unit tests cover raw-only total of 2 stages, improved total of 3 stages, quoted/escaped context values, provider/model context, artifact context, and fail context.
- Context compact: Pipeline emits quoted `PROGRESS` lines for raw/improved stages with contextual fields and failure status.

### 23. Implement CLI Argument Parsing

- [x] Implement a Go CLI with Python-compatible flags: positional video file, `--provider`, `--model`, `--language`, `--improve-subtitles`, and `--output`/`-o`.
- Acceptance criteria: unit tests cover defaults, missing video file, `--output` requiring `--improve-subtitles`, provider/model/language forwarding, improved output override, stderr success message, and non-zero error behavior.
- Context compact: `cmd/video-to-srt` parses compatible flags, validates output/improve coupling and missing video, runs pipeline, and prints `Wrote`.

### 24. Implement Provider Discoverability Command

- [x] Add the provider/model discoverability command or equivalent CLI/API required by OpenSpec.
- Acceptance criteria: unit tests confirm output includes all registered providers, default models, supported model lists, and parseable JSON or another clearly parseable format.
- Context compact: `video-to-srt providers`/`list-providers` prints provider/model JSON from the registry.

### 25. Add Spec Traceability Matrix

- [x] Add or update a matrix mapping OpenSpec requirements to Go packages/tests.
- Acceptance criteria: every requirement section listed in `OpenSpec Scope` above has at least one Go implementation/test reference or an explicit deferred note.
- Context compact: Added `go/TRACEABILITY.md` mapping OpenSpec capabilities to packages/tests/status.

### 26. Add Go README

- [x] Document setup, build/test commands, ffmpeg requirement, env vars, supported providers/models, outputs, and Python-reference status under `go/`.
- Acceptance criteria: README examples preserve current CLI behavior and clearly state that Python remains available as reference.
- Context compact: Added `go/README.md` with setup, build/test, ffmpeg, CLI examples, env vars, outputs, providers, and Python reference bridge notes.

### 27. Run Full Go Unit Test Suite

- [x] Run `go test ./...` from `go/` and fix failures.
- Acceptance criteria: all Go unit tests pass locally; any skipped external-provider tests are explicitly documented with reasons.
- Context compact: `go test ./...` passes from `go/`.

### 28. Manual Smoke Test With Real ffmpeg

- [ ] Run the Go binary on a small local media sample using a fake or low-cost provider path where possible.
- Acceptance criteria: audio extraction works with installed `ffmpeg`, artifact names match Python, progress appears on stderr, and cleanup behavior matches OpenSpec.
- Context compact: pending.

### 29. Parity Review Against Python Reference

- [x] Compare the Go behavior against the Python reference for deterministic components and documented CLI behavior.
- Acceptance criteria: SRT parser/formatter/validator/improver parity is documented; any intentional differences are listed with rationale and linked to OpenSpec.
- Context compact: Deterministic parity documented in `go/TRACEABILITY.md`; provider bridge preserves Python reference behavior for SDK/native providers.

### 30. Release Readiness Check

- [x] Decide whether the Go implementation is ready for regular use while keeping Python as reference.
- Acceptance criteria: feature parity status is summarized, known gaps are listed, test status is current, and next adoption step is explicit.
- Context compact: Go implementation is test-ready with Python kept as operational reference for Voxtral/Vertex/Sherpa provider calls; real-ffmpeg smoke remains pending.

## Deferred Or Risky Areas

- Voxtral Go API details may require SDK usage if direct HTTP is not stable or documented enough.
- Vertex Gemini direct HTTP/ADC implementation may require Google auth helpers even if the provider API is wrapped behind a small interface.
- Sherpa Parakeet native recognition from Go may require shelling out, CGO, or another integration path; keep this isolated behind the provider boundary.
- Subtitle improvement parity should be treated as deterministic and heavily unit-tested because small differences can change output bytes.
- Integration tests against real cloud providers are intentionally outside the initial unit-test bar unless added later.
