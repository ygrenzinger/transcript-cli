## ADDED Requirements

### Requirement: Input source resolution

The capability SHALL resolve a user-supplied input source into a local video file path suitable for audio extraction. The input source SHALL be either an existing local video file path or a supported YouTube URL.

#### Scenario: Existing local video path

- GIVEN an input source `path/to/clip.mp4` that exists on disk
- WHEN source ingestion resolves the input
- THEN it returns `path/to/clip.mp4`
- AND it does not invoke `yt-dlp`

#### Scenario: Missing local video path

- GIVEN an input source `path/to/missing.mp4` that does not exist on disk
- WHEN source ingestion resolves the input
- THEN it fails with a non-zero result or exception
- AND the error states that the local file was not found
- AND it does not invoke `yt-dlp`

### Requirement: YouTube URL download

The capability SHALL support YouTube URLs by invoking the installed `yt-dlp` executable to download exactly one local video file before downstream processing begins.

#### Scenario: Download YouTube URL

- GIVEN an input source `https://www.youtube.com/watch?v=abc123` and `yt-dlp` is available
- WHEN source ingestion resolves the input
- THEN it invokes `yt-dlp` non-interactively for that URL
- AND it returns the downloaded local video path
- AND the returned path exists before audio extraction begins

#### Scenario: Short YouTube URL

- GIVEN an input source `https://youtu.be/abc123` and `yt-dlp` is available
- WHEN source ingestion resolves the input
- THEN it treats the input as a supported YouTube URL
- AND it returns the downloaded local video path

#### Scenario: yt-dlp unavailable

- GIVEN an input source that is a supported YouTube URL
- AND the `yt-dlp` executable is not available
- WHEN source ingestion resolves the input
- THEN it fails before audio extraction begins
- AND the error states that `yt-dlp` is required for YouTube URLs

#### Scenario: yt-dlp download failure

- GIVEN an input source that is a supported YouTube URL
- AND `yt-dlp` exits non-zero
- WHEN source ingestion resolves the input
- THEN it fails before audio extraction begins
- AND the error states that the YouTube download failed

### Requirement: Unsupported URL rejection

The capability SHALL reject HTTP(S) URLs that are not recognized YouTube URLs before invoking `yt-dlp`.

#### Scenario: Unsupported HTTP URL

- GIVEN an input source `https://example.com/video.mp4`
- WHEN source ingestion resolves the input
- THEN it fails before audio extraction begins
- AND the error states that only local video files and YouTube URLs are supported
- AND it does not invoke `yt-dlp`
