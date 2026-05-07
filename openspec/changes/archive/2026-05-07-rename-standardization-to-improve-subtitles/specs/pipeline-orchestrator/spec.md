## MODIFIED Requirements

### Requirement: End-to-end pipeline
Given a video path and a chosen provider, the orchestrator SHALL execute audio extraction and audio-to-SRT transcription via the selected provider. The raw transcription output SHALL be written next to the source video as `<video>.<provider>.raw.srt`. If subtitle improvement is requested, the orchestrator SHALL additionally run subtitle improvement and write `<video>.<provider>.improved.srt`.

#### Scenario: Raw-only happy path
- **GIVEN** a video at `path/to/clip.mp4`, the required API credentials in the environment, and a registered provider `voxtral`
- **WHEN** the orchestrator is invoked with `path/to/clip.mp4` and `--provider voxtral`
- **THEN** it produces `path/to/clip.voxtral.raw.srt`
- **AND** it does not produce `path/to/clip.voxtral.improved.srt`
- **AND** audio extraction and transcription have each been executed exactly once

#### Scenario: Improved happy path
- **GIVEN** a video at `path/to/clip.mp4`, the required API credentials in the environment, and a registered provider `voxtral`
- **WHEN** the orchestrator is invoked with `path/to/clip.mp4`, `--provider voxtral`, and subtitle improvement enabled
- **THEN** it produces `path/to/clip.voxtral.raw.srt`
- **AND** it produces `path/to/clip.voxtral.improved.srt`
- **AND** the improved file passes `srt-validation`

### Requirement: Stage isolation and swappability
Each stage SHALL be invoked through a stable interface that does not depend on the implementation details of other stages. Replacing one stage's implementation SHALL NOT require changes to the others. Subtitle improvement SHALL consume raw SRT through the same SRT parser and SHALL NOT depend on provider-specific implementation details beyond the artifact path.

#### Scenario: Replace the extractor
- **GIVEN** the audio-extraction implementation is replaced
- **WHEN** the orchestrator runs
- **THEN** the transcription and optional subtitle-improvement stages work without modification, provided the new extractor still produces an MP3 at the agreed path

#### Scenario: Add a new transcription provider
- **GIVEN** a third provider is added by registering it under a new name
- **WHEN** the user selects it via `--provider`
- **THEN** it is invoked through the same provider interface
- **AND** optional subtitle improvement processes its raw SRT output unchanged

### Requirement: Validation gate
The orchestrator SHALL validate improved subtitle output before declaring the improvement step successful. The orchestrator SHALL NOT require strict raw SRT validation before subtitle improvement, because subtitle improvement is responsible for tolerating provider artifacts such as non-positive-duration cues that can be safely removed.

#### Scenario: Raw provider output contains removable invalid cue
- **GIVEN** a provider raw SRT contains a cue whose end timestamp equals its start timestamp
- **WHEN** the orchestrator runs with subtitle improvement enabled
- **THEN** subtitle improvement removes that cue
- **AND** the orchestrator validates the improved output

#### Scenario: Improved output fails validation
- **GIVEN** subtitle improvement produces a file that does not pass validation
- **WHEN** the orchestrator runs the post-improvement validation
- **THEN** it fails the run with a clear error
- **AND** the bug is treated as a defect in the subtitle-improvement step, not the user's input

### Requirement: Stage progress reporting
The orchestrator SHALL report the start and completion of each executed stage on stderr, so that the user can follow progress on a long video. Progress totals SHALL reflect whether optional subtitle improvement is enabled.

#### Scenario: Raw-only progress lines
- **GIVEN** the orchestrator is invoked without subtitle improvement
- **WHEN** it runs
- **THEN** it emits progress lines for audio extraction and transcription
- **AND** the progress total reflects only executed stages

#### Scenario: Improved progress lines
- **GIVEN** the orchestrator is invoked with subtitle improvement enabled
- **WHEN** it runs
- **THEN** it emits progress lines for audio extraction, transcription, and subtitle improvement
- **AND** the progress total reflects all executed stages

### Requirement: Intermediate artifacts
Intermediate files, including extracted audio and raw provider SRT, MAY be persisted next to the source video for caching and debugging. Raw provider SRT SHALL be preserved as `<video>.<provider>.raw.srt`. Improved SRT SHALL be written as `<video>.<provider>.improved.srt` only when subtitle improvement is enabled.

#### Scenario: Cached audio reused
- **GIVEN** a previous run already produced `path/to/clip.mp3`
- **WHEN** the orchestrator runs again on `path/to/clip.mp4`
- **THEN** it MAY reuse the existing MP3 instead of re-extracting
- **AND** it still re-runs transcription
- **AND** it runs subtitle improvement only when requested

#### Scenario: Multiple providers do not overwrite improved artifacts
- **GIVEN** `voxtral` and `grok` are registered providers
- **WHEN** the user runs improved transcription with both providers for `path/to/clip.mp4`
- **THEN** the pipeline writes separate improved files for each provider
- **AND** the provider name appears in each improved SRT filename

### Requirement: Single-command UX
The orchestrator SHALL be invocable with a single command requiring only the video path and credentials in environment variables. No interactive prompts or manual file shuffling SHALL be required. Subtitle improvement SHALL be enabled with an explicit CLI option or equivalent non-interactive configuration.

#### Scenario: One-shot raw run
- **GIVEN** a video and the required API key set in the environment
- **WHEN** the user runs the orchestrator with the video as the only positional argument
- **THEN** a raw provider SRT file is produced next to the video without further interaction

#### Scenario: One-shot improved run
- **GIVEN** a video and the required API key set in the environment
- **WHEN** the user runs the orchestrator with the video and the subtitle-improvement option
- **THEN** a raw provider SRT file and an improved SRT file are produced next to the video without further interaction

#### Scenario: Missing credentials
- **GIVEN** the required API key environment variable is not set
- **WHEN** the user runs the orchestrator
- **THEN** it exits with a non-zero status before any stage runs
- **AND** the error names the missing environment variable
