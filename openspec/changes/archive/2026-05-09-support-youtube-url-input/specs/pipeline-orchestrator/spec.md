## MODIFIED Requirements

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

### Requirement: Single-command UX

The orchestrator SHALL be invocable with a single command requiring only an input source and credentials or provider-specific configuration in environment variables. The input source SHALL be either a local video file path or a supported YouTube URL. No interactive prompts or manual file shuffling SHALL be required. Subtitle improvement SHALL be enabled with an explicit CLI option or equivalent non-interactive configuration.

#### Scenario: One-shot local raw run

- GIVEN a local video file and the required API key set in the environment
- WHEN the user runs the orchestrator with the video path as the only positional argument
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
- THEN it exits with a non-zero status before audio extraction or transcription runs
- AND the error names the missing configuration value
