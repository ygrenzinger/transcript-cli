## Why

The pipeline currently leaves the extracted MP3 on disk after transcription, which creates unnecessary local storage usage and leaves transient artifacts beside the source video. Once the raw SRT has been successfully written, the extracted audio is no longer needed for the completed run.

## What Changes

- Remove the extracted audio file after the raw provider SRT has been created successfully.
- Preserve existing output behavior for raw and improved SRT files.
- Keep failure behavior safe: if extraction or transcription fails before raw SRT creation, do not attempt to remove files that may still be needed for troubleshooting.
- **BREAKING**: The pipeline will no longer persist extracted audio as a reusable intermediate artifact after successful raw SRT creation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `pipeline-orchestrator`: Change intermediate artifact handling so extracted audio is deleted after successful raw SRT creation.

## Impact

- Affects the end-to-end pipeline orchestration in `python/transcribe.py`.
- Affects tests that assert pipeline filesystem outputs in `python/test_pipeline_outputs.py`.
- No new runtime dependencies or external APIs are required.
