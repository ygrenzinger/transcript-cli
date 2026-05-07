## 1. Pipeline Cleanup

- [x] 1.1 Update `python/transcribe.py` so `run_pipeline` removes the extracted audio path after successful raw SRT creation.
- [x] 1.2 Ensure cleanup does not run when extraction or transcription fails before raw SRT creation.
- [x] 1.3 Ensure raw-only and improved runs still return the same SRT output paths and preserve their SRT files.

## 2. Tests

- [x] 2.1 Update pipeline output tests to assert extracted audio is removed after successful raw-only runs.
- [x] 2.2 Update pipeline output tests to assert extracted audio is removed after successful improved runs while raw and improved SRT files remain.
- [x] 2.3 Add or update a failure-path test to assert extracted audio is retained when transcription fails.

## 3. Verification

- [x] 3.1 Run the Python test suite covering pipeline outputs.
- [x] 3.2 Run OpenSpec validation/status checks for `remove-audio-after-raw-srt-created`.
