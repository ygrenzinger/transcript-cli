# audio-extraction Specification

## Purpose
Extract the audio track from a video file into a standalone audio file suitable for downstream speech-to-text transcription. This capability is concerned only with audio extraction — it does not transcribe, validate timing, or know about subtitles.

## Requirements

### Requirement: Video input acceptance
The capability SHALL accept any video file readable by ffmpeg (e.g. MP4, MOV, MKV, WebM, AVI).

#### Scenario: Common video container
- GIVEN a valid video file in MP4, MOV, MKV, WebM, or AVI format
- WHEN the extractor is invoked with the file path
- THEN extraction proceeds without error

#### Scenario: Missing or unreadable file
- GIVEN a path that does not exist or is not a video readable by ffmpeg
- WHEN the extractor is invoked
- THEN it exits with a non-zero status and a clear error message
- AND no output file is created

### Requirement: MP3 output
The capability SHALL produce a single MP3 file as output. The output path SHALL default to the input video's stem with a `.mp3` suffix, written next to the source video.

#### Scenario: Default output location
- GIVEN an input video at `path/to/clip.mp4`
- WHEN the extractor runs with default options
- THEN an MP3 is produced at `path/to/clip.mp3`
- AND the source video is unchanged

### Requirement: Audio track presence
If the source video has no audio track, the capability SHALL fail explicitly rather than producing an empty or silent output file.

#### Scenario: Video without audio
- GIVEN a video that contains no audio stream
- WHEN the extractor runs
- THEN it exits with a non-zero status and an error explaining no audio was found
- AND no MP3 file is produced

### Requirement: Idempotent re-extraction
Re-running extraction over the same input SHALL be safe and produce the same output. Existing outputs MAY be reused as a cache.

#### Scenario: Output already exists
- GIVEN an MP3 already exists at the target output path from a prior run of the same input
- WHEN the extractor is invoked again
- THEN it either overwrites the file with an equivalent result or skips extraction and reports the cache hit
- AND downstream consumers can rely on the output file being present and valid
