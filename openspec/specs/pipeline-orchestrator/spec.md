# pipeline-orchestrator Specification

## Purpose
Compose the four lower-level capabilities (`audio-extraction`, `audio-to-srt-transcription`, `srt-validation`, `srt-standardization`) into a single end-to-end pipeline that turns a video file into a polished SRT file. The orchestrator is the only component that knows the order of stages and how they are wired; each stage remains independently swappable. This is what gives the user a one-command experience while still letting them choose which transcription provider/model to use.

## Requirements

### Requirement: End-to-end pipeline
Given a video path and a chosen provider, the orchestrator SHALL execute the following stages in order: (1) audio extraction, (2) audio-to-SRT transcription via the selected provider, (3) SRT validation, (4) SRT standardization. The final output SHALL be a single `.srt` file written next to the source video.

#### Scenario: Happy path
- GIVEN a video at `path/to/clip.mp4`, the required API credentials in the environment, and a registered provider
- WHEN the orchestrator is invoked with `path/to/clip.mp4` and the provider name
- THEN it produces `path/to/clip.srt`
- AND each of the four stages has been executed exactly once
- AND the final file passes `srt-validation`

### Requirement: Provider and model selection
The orchestrator SHALL expose a `--provider` option (or equivalent) to select between registered transcription providers (e.g. `voxtral`, `grok`) and a `--model` option for providers that expose model selection. Defaults SHALL be documented and stable. The `voxtral` provider SHALL expose exactly one supported model, `voxtral-mini-2602`, and SHALL use it by default.

#### Scenario: Switch provider
- GIVEN providers `voxtral` and `grok` are registered
- WHEN the user runs the pipeline with `--provider grok`
- THEN the Grok-backed provider is used for the transcription stage
- AND switching to `--provider voxtral` re-runs the same audio through the Voxtral-backed provider

#### Scenario: Voxtral default model
- GIVEN provider `voxtral` is selected
- WHEN the user omits `--model`
- THEN the pipeline uses `voxtral-mini-2602`

#### Scenario: Explicit Voxtral model
- GIVEN provider `voxtral` is selected
- WHEN the user runs the pipeline with `--provider voxtral --model voxtral-mini-2602`
- THEN the pipeline uses `voxtral-mini-2602`

#### Scenario: Unknown provider or model
- GIVEN a provider or model name that is not registered
- WHEN the user invokes the pipeline
- THEN it exits with a non-zero status before any stage runs
- AND the error message lists available providers (or models for the given provider)

### Requirement: Stage isolation and swappability
Each stage SHALL be invoked through a stable interface that does not depend on the implementation details of other stages. Replacing one stage's implementation SHALL NOT require changes to the others.

#### Scenario: Replace the extractor
- GIVEN the audio-extraction implementation is replaced (e.g. moviepy → ffmpeg-python)
- WHEN the orchestrator runs
- THEN the transcription, validation, and standardization stages work without modification, provided the new extractor still produces an MP3 at the agreed path

#### Scenario: Add a new transcription provider
- GIVEN a third provider is added by registering it under a new name
- WHEN the user selects it via `--provider`
- THEN it is invoked through the same provider interface, and the validation and standardization stages process its output unchanged

### Requirement: Validation gate
The orchestrator SHALL run `srt-validation` on the provider's raw output before standardization, and again on the standardized output before declaring success. If either validation fails, the orchestrator SHALL exit with a non-zero status.

#### Scenario: Provider output fails validation
- GIVEN a provider that produces a malformed SRT (e.g. broken timestamps)
- WHEN the orchestrator runs
- THEN the first validation step fails
- AND the orchestrator exits with a non-zero status reporting the validation error
- AND no `.srt` file is delivered to the user

#### Scenario: Standardization output fails validation
- GIVEN standardization produces a file that does not pass validation
- WHEN the orchestrator runs the post-standardization validation
- THEN it fails the run with a clear error
- AND the bug is treated as a defect in the standardization step, not the user's input

### Requirement: Stage progress reporting
The orchestrator SHALL report the start and completion of each stage on stderr, so that the user can follow progress on a long video.

#### Scenario: Progress lines
- GIVEN the orchestrator is invoked
- WHEN it runs
- THEN it emits at least one line per stage to stderr (e.g. `[1/4] Extracting audio…`, `[2/4] Transcribing with grok…`, `[3/4] Validating…`, `[4/4] Standardizing…`)

### Requirement: Failure stops the pipeline
If any stage exits non-zero, the orchestrator SHALL stop, propagate the non-zero status, and NOT run subsequent stages.

#### Scenario: Transcription provider fails
- GIVEN the transcription provider exits with a non-zero status
- WHEN the orchestrator handles that result
- THEN it stops the pipeline immediately
- AND it does not run validation or standardization
- AND it returns the provider's non-zero exit status (or wraps it)

### Requirement: Intermediate artifacts
Intermediate files (extracted audio, raw provider SRT) MAY be persisted next to the source video for caching and debugging. They SHALL NOT block the user — the user only ever needs to provide the video and credentials.

#### Scenario: Cached audio reused
- GIVEN a previous run already produced `path/to/clip.mp3`
- WHEN the orchestrator runs again on `path/to/clip.mp4`
- THEN it MAY reuse the existing MP3 (per `audio-extraction`'s idempotence rule) instead of re-extracting
- AND it still re-runs transcription, validation, and standardization

### Requirement: Single-command UX
The orchestrator SHALL be invocable with a single command requiring only the video path and credentials in environment variables. No interactive prompts or manual file shuffling SHALL be required.

#### Scenario: One-shot run
- GIVEN a video and the required API key set in the environment
- WHEN the user runs the orchestrator with the video as the only positional argument
- THEN a `.srt` file is produced next to the video without further interaction

#### Scenario: Missing credentials
- GIVEN the required API key environment variable is not set
- WHEN the user runs the orchestrator
- THEN it exits with a non-zero status before any stage runs
- AND the error names the missing environment variable
