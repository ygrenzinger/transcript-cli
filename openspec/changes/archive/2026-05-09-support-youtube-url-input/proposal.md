## Why

The transcript tool currently requires a local video file path. Many source videos live on YouTube, which forces users to manually download the video before running the transcription pipeline. Since `yt-dlp` is available in the environment, the tool can provide a single-command path for YouTube URLs while preserving the existing local-file workflow.

## What Changes

- Accept either a local video file path or a YouTube URL as the pipeline input.
- For YouTube URLs, invoke `yt-dlp` non-interactively to download a local video file before audio extraction runs.
- Use the downloaded video's resolved local path as the source for existing artifact naming and downstream stages.
- Keep `audio-extraction` focused on local files; URL handling happens before audio extraction.
- Fail early with a clear error when URL download fails or `yt-dlp` is unavailable.

## Capabilities

### New Capabilities

- `video-source-ingestion`: Resolve a user-supplied input source into a local video file, using `yt-dlp` for YouTube URLs.

### Modified Capabilities

- `pipeline-orchestrator`: Accept a generic input source, resolve it to a local video file, then run the existing extraction, transcription, optional improvement, validation, and artifact lifecycle stages.

## Impact

- Affects CLI argument validation and pipeline setup in `python/transcribe.py`.
- Adds a runtime dependency on the `yt-dlp` executable for YouTube URL input only.
- Affects tests around pipeline input handling and artifact naming in `python/test_pipeline_outputs.py` or a new focused test module.
- Does not change provider selection, transcription provider interfaces, or subtitle improvement behavior.

## Non-Goals

- Support arbitrary non-YouTube video sites beyond what is explicitly accepted as a YouTube URL.
- Stream directly from YouTube into the transcription provider without a local downloaded file.
- Add interactive prompts for choosing video formats or filenames.
