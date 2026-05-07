## MODIFIED Requirements

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
