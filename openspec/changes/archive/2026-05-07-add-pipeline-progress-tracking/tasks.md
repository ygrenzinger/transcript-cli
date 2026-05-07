## 1. Progress Model

- [x] 1.1 Define the pipeline stage metadata in `python/pipeline.py`, including stage number, total stages, stage name, and optional context fields.
- [x] 1.2 Add a small progress emission helper that writes structured `START`, `DONE`, and `FAIL` events to stderr.
- [x] 1.3 Add a stage runner wrapper that emits start/completion/failure progress while preserving original exceptions.

## 2. Pipeline Integration

- [x] 2.1 Wrap audio extraction, transcription, validation, and standardization calls with the stage runner.
- [x] 2.2 Include provider and resolved/requested model context in transcription progress output.
- [x] 2.3 Include relevant artifact paths in completion output where available.
- [x] 2.4 Ensure later stages do not emit progress after an earlier stage fails.

## 3. Verification

- [x] 3.1 Add or update tests for successful stderr progress across all four stages.
- [x] 3.2 Add or update tests for provider/model context in transcription progress.
- [x] 3.3 Add or update tests for failure progress and stop-on-failure behavior.
- [x] 3.4 Run the relevant test suite or CLI smoke checks and fix regressions.
