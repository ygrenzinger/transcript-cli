# pipeline-orchestrator Specification

## Purpose
Compose the lower-level capabilities (`video-source-ingestion`, `audio-extraction`, `audio-to-srt-transcription`, optional `subtitle-improvement`, and `srt-validation` for improved output) into a single end-to-end pipeline that turns an input source into provider-specific SRT artifacts. The orchestrator is the only component that knows the order of stages and how they are wired; each stage remains independently swappable. This is what gives the user a one-command experience while still letting them choose which transcription provider/model to use.
## Requirements
### Requirement: End-to-end pipeline
Given an input source and a chosen provider, the orchestrator SHALL resolve the input source to a local video path, then execute audio extraction and audio-to-SRT transcription via the selected provider. The raw transcription output SHALL be written next to the resolved source video as `<video>.<provider>.raw.srt`. If subtitle improvement is requested, the orchestrator SHALL additionally run subtitle improvement and write `<video>.<provider>.improved.srt`.

#### Scenario: Raw-only happy path
- GIVEN a video at `path/to/clip.mp4`, the required API credentials in the environment, and a registered provider `voxtral`
- WHEN the orchestrator is invoked with `path/to/clip.mp4` and `--provider voxtral`
- THEN it produces `path/to/clip.voxtral.raw.srt`
- AND it does not produce `path/to/clip.voxtral.improved.srt`
- AND audio extraction and transcription have each been executed exactly once

#### Scenario: Improved happy path
- GIVEN a video at `path/to/clip.mp4`, the required API credentials in the environment, and a registered provider `voxtral`
- WHEN the orchestrator is invoked with `path/to/clip.mp4`, `--provider voxtral`, and subtitle improvement enabled
- THEN it produces `path/to/clip.voxtral.raw.srt`
- AND it produces `path/to/clip.voxtral.improved.srt`
- AND the improved file passes `srt-validation`

#### Scenario: YouTube URL happy path
- GIVEN a supported YouTube URL, `yt-dlp` is available, the required API credentials are in the environment, and a registered provider `voxtral`
- WHEN the orchestrator is invoked with the YouTube URL and `--provider voxtral`
- THEN it resolves the URL to a downloaded local video path before audio extraction
- AND it produces `<downloaded-video>.voxtral.raw.srt` next to the downloaded video
- AND audio extraction and transcription have each been executed exactly once against the downloaded video

### Requirement: Provider and model selection
The orchestrator SHALL expose a `--provider` option (or equivalent) to select between registered transcription providers (e.g. `voxtral`, `grok`, `vertex-gemini`) and a `--model` option for providers that expose model selection. Defaults SHALL be documented and stable. The `voxtral` provider SHALL expose exactly one supported model, `voxtral-mini-2602`, and SHALL use it by default. The `vertex-gemini` provider SHALL expose `gemini-2.5-flash` and `gemini-2.5-pro`, and SHALL use `gemini-2.5-flash` by default.

#### Scenario: Switch provider
- GIVEN providers `voxtral`, `grok`, and `vertex-gemini` are registered
- WHEN the user runs the pipeline with `--provider grok`
- THEN the Grok-backed provider is used for the transcription stage
- AND switching to `--provider voxtral` re-runs the same audio through the Voxtral-backed provider
- AND switching to `--provider vertex-gemini` re-runs the same audio through the Vertex Gemini-backed provider

#### Scenario: Voxtral default model
- GIVEN provider `voxtral` is selected
- WHEN the user omits `--model`
- THEN the pipeline uses `voxtral-mini-2602`

#### Scenario: Explicit Voxtral model
- GIVEN provider `voxtral` is selected
- WHEN the user runs the pipeline with `--provider voxtral --model voxtral-mini-2602`
- THEN the pipeline uses `voxtral-mini-2602`

#### Scenario: Vertex Gemini default model
- GIVEN provider `vertex-gemini` is selected
- WHEN the user omits `--model`
- THEN the pipeline uses `gemini-2.5-flash`

#### Scenario: Explicit Vertex Gemini model
- GIVEN provider `vertex-gemini` is selected
- WHEN the user runs the pipeline with `--provider vertex-gemini --model gemini-2.5-flash`
- THEN the pipeline uses `gemini-2.5-flash`

#### Scenario: Explicit Vertex Gemini Pro model
- GIVEN provider `vertex-gemini` is selected
- WHEN the user runs the pipeline with `--provider vertex-gemini --model gemini-2.5-pro`
- THEN the pipeline uses `gemini-2.5-pro`

#### Scenario: Unknown provider or model
- GIVEN a provider or model name that is not registered
- WHEN the user invokes the pipeline
- THEN it exits with a non-zero status before any stage runs
- AND the error message lists available providers (or models for the given provider)

### Requirement: Stage isolation and swappability
Each stage SHALL be invoked through a stable interface that does not depend on the implementation details of other stages. Replacing one stage's implementation SHALL NOT require changes to the others. Subtitle improvement SHALL consume raw SRT through the same SRT parser and SHALL NOT depend on provider-specific implementation details beyond the artifact path.

#### Scenario: Replace the extractor
- GIVEN the audio-extraction implementation is replaced
- WHEN the orchestrator runs
- THEN the transcription and optional subtitle-improvement stages work without modification, provided the new extractor still produces an MP3 at the agreed path

#### Scenario: Add a new transcription provider
- GIVEN a third provider is added by registering it under a new name
- WHEN the user selects it via `--provider`
- THEN it is invoked through the same provider interface
- AND optional subtitle improvement processes its raw SRT output unchanged

#### Scenario: Add Vertex Gemini without orchestrator-specific provider logic
- GIVEN provider `vertex-gemini` is registered by the transcription capability
- WHEN the user selects it via `--provider vertex-gemini`
- THEN the orchestrator invokes it through the shared provider interface
- AND the orchestrator does not contain Vertex-specific API, authentication, prompt, or response parsing logic

### Requirement: Validation gate
The orchestrator SHALL validate improved subtitle output before declaring the improvement step successful. The orchestrator SHALL NOT require strict raw SRT validation before subtitle improvement, because subtitle improvement is responsible for tolerating provider artifacts such as non-positive-duration cues that can be safely removed.

#### Scenario: Raw provider output contains removable invalid cue
- GIVEN a provider raw SRT contains a cue whose end timestamp equals its start timestamp
- WHEN the orchestrator runs with subtitle improvement enabled
- THEN subtitle improvement removes that cue
- AND the orchestrator validates the improved output

#### Scenario: Improved output fails validation
- GIVEN subtitle improvement produces a file that does not pass validation
- WHEN the orchestrator runs the post-improvement validation
- THEN it fails the run with a clear error
- AND the bug is treated as a defect in the subtitle-improvement step, not the user's input

### Requirement: Stage progress reporting
The orchestrator SHALL report the start and completion of each executed stage on stderr, so that the user can follow progress on a long video. Progress totals SHALL reflect whether optional subtitle improvement is enabled.

#### Scenario: Raw-only progress lines
- GIVEN the orchestrator is invoked without subtitle improvement
- WHEN it runs
- THEN it emits progress lines for audio extraction and transcription
- AND the progress total reflects only executed stages

#### Scenario: Improved progress lines
- GIVEN the orchestrator is invoked with subtitle improvement enabled
- WHEN it runs
- THEN it emits progress lines for audio extraction, transcription, and subtitle improvement
- AND the progress total reflects all executed stages

### Requirement: Failure stops the pipeline
If input source resolution or any later stage exits non-zero, the orchestrator SHALL stop, propagate the non-zero status, and NOT run subsequent stages.

#### Scenario: YouTube download fails
- GIVEN the input source is a supported YouTube URL
- AND `yt-dlp` fails to download the video
- WHEN the orchestrator handles that result
- THEN it stops the pipeline immediately
- AND it does not run audio extraction, transcription, validation, or subtitle improvement
- AND it returns a non-zero status with a clear download error

#### Scenario: Transcription provider fails
- GIVEN the transcription provider exits with a non-zero status
- WHEN the orchestrator handles that result
- THEN it stops the pipeline immediately
- AND it does not run validation or subtitle improvement
- AND it returns the provider's non-zero exit status (or wraps it)

### Requirement: Intermediate artifacts
Intermediate files SHALL be managed by the orchestrator according to their lifecycle. Raw provider SRT SHALL be preserved as `<video>.<provider>.raw.srt`. Improved SRT SHALL be written as `<video>.<provider>.improved.srt` only when subtitle improvement is enabled. Extracted audio SHALL be removed after successful raw SRT creation and SHALL NOT be preserved as a reusable intermediate artifact for successful runs.

#### Scenario: Audio removed after raw SRT creation
- GIVEN a video at `path/to/clip.mp4` and a registered provider `voxtral`
- WHEN the orchestrator successfully writes `path/to/clip.voxtral.raw.srt`
- THEN `path/to/clip.mp3` is removed from the filesystem
- AND `path/to/clip.voxtral.raw.srt` remains on the filesystem

#### Scenario: Audio retained when transcription fails
- GIVEN audio extraction produced `path/to/clip.mp3`
- WHEN the transcription provider exits with a non-zero status before writing a valid raw SRT
- THEN the orchestrator stops the pipeline
- AND it does not remove `path/to/clip.mp3`

#### Scenario: Multiple providers do not overwrite improved artifacts
- GIVEN `voxtral` and `grok` are registered providers
- WHEN the user runs improved transcription with both providers for `path/to/clip.mp4`
- THEN the pipeline writes separate improved files for each provider
- AND the provider name appears in each improved SRT filename
- AND extracted audio from each successful run is removed after that run's raw SRT is created

### Requirement: Single-command UX
The orchestrator SHALL be invocable with a single command requiring only an input source and credentials or provider-specific configuration in environment variables. The input source SHALL be either a local video file path or a supported YouTube URL. No interactive prompts or manual file shuffling SHALL be required. Subtitle improvement SHALL be enabled with an explicit CLI option or equivalent non-interactive configuration.

#### Scenario: One-shot local raw run
- GIVEN a video and the required API key set in the environment
- WHEN the user runs the orchestrator with the video as the only positional argument
- THEN a raw provider SRT file is produced next to the video without further interaction

#### Scenario: One-shot YouTube raw run
- GIVEN a supported YouTube URL, `yt-dlp` is available, and the required API key is set in the environment
- WHEN the user runs the orchestrator with the URL as the only positional argument
- THEN the video is downloaded automatically
- AND a raw provider SRT file is produced next to the downloaded video without further interaction

#### Scenario: One-shot improved run
- GIVEN an input source and the subtitle-improvement option
- WHEN the user runs the orchestrator with the required provider configuration in the environment
- THEN a raw provider SRT file and an improved SRT file are produced without further interaction

#### Scenario: Missing credentials
- GIVEN the selected provider's required configuration is not set
- WHEN the user runs the orchestrator
- THEN it exits with a non-zero status before any stage runs
- AND the error names the missing configuration value

#### Scenario: One-shot Vertex Gemini run
- GIVEN a video, valid Google Application Default Credentials, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`
- WHEN the user runs the orchestrator with `--provider vertex-gemini`
- THEN a raw Vertex Gemini SRT file is produced next to the video without further interaction

### Requirement: Sherpa Parakeet pipeline selection
The orchestrator SHALL allow users to select the registered `sherpa-parakeet` transcription provider with the same provider/model selection mechanism used by other providers. The orchestrator SHALL invoke `sherpa-parakeet` only through the shared transcription provider interface and SHALL NOT contain sherpa-onnx-specific model, cache, runtime, or audio conversion logic.

#### Scenario: Run pipeline with Sherpa Parakeet
- **GIVEN** provider `sherpa-parakeet` is registered
- **WHEN** the user runs the pipeline with `--provider sherpa-parakeet`
- **THEN** the orchestrator invokes the Sherpa Parakeet-backed provider for the transcription stage
- **AND** the raw transcription output is written as `<video>.sherpa-parakeet.raw.srt`

#### Scenario: Explicit Sherpa Parakeet model
- **GIVEN** provider `sherpa-parakeet` is registered
- **WHEN** the user runs the pipeline with `--provider sherpa-parakeet --model parakeet-tdt-0.6b-v3-int8`
- **THEN** the orchestrator validates the provider-scoped model before running stages
- **AND** the Sherpa Parakeet provider uses `parakeet-tdt-0.6b-v3-int8`

#### Scenario: No orchestrator-specific Sherpa logic
- **GIVEN** provider `sherpa-parakeet` is registered by the transcription capability
- **WHEN** the user selects it via `--provider sherpa-parakeet`
- **THEN** the orchestrator invokes it through the shared provider interface
- **AND** the orchestrator does not contain sherpa-onnx-specific download, cache, runtime, model-file, or audio conversion logic
