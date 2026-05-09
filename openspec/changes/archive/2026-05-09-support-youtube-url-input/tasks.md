## 1. Source Ingestion

- [x] 1.1 Add input-source resolution that accepts a local path or YouTube URL and returns a local video path.
- [x] 1.2 Detect supported YouTube URL hosts and reject unsupported HTTP(S) URLs with a clear error.
- [x] 1.3 Invoke `yt-dlp` non-interactively for YouTube URLs and capture the downloaded file path.
- [x] 1.4 Fail before audio extraction when `yt-dlp` is unavailable or download exits non-zero.

## 2. Pipeline Integration

- [x] 2.1 Update the CLI positional argument from local-only video path semantics to input-source semantics.
- [x] 2.2 Run existing extraction, transcription, optional improvement, validation, and audio cleanup stages against the resolved local video path.
- [x] 2.3 Ensure URL-input artifacts use the downloaded video's stem and provider name for raw and improved SRT filenames.
- [x] 2.4 Preserve existing local-file behavior and error messages where practical.

## 3. Tests

- [x] 3.1 Add tests for local path input continuing through the existing pipeline unchanged.
- [x] 3.2 Add tests for YouTube URL input invoking the downloader and then the pipeline with the resolved local path.
- [x] 3.3 Add tests for unsupported HTTP(S) URLs.
- [x] 3.4 Add tests for missing or failing `yt-dlp` preventing downstream stages from running.

## 4. Verification

- [x] 4.1 Run the Python test suite covering pipeline input handling and outputs.
- [x] 4.2 Run OpenSpec validation/status checks for `support-youtube-url-input`.
