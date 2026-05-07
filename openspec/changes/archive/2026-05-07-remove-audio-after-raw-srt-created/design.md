## Context

The pipeline extracts audio to `<video>.mp3`, passes that file to the selected transcription provider, and writes a raw SRT file as `<video>.<provider>.raw.srt`. The existing orchestrator spec allows intermediate artifacts, including extracted audio, to be persisted for caching and debugging. The requested behavior changes that lifecycle: once the raw SRT exists, the extracted audio should be treated as disposable.

## Goals / Non-Goals

**Goals:**

- Delete the extracted audio file only after transcription has completed successfully and the raw SRT has been written.
- Preserve raw and improved SRT output paths and existing provider/model behavior.
- Keep failure behavior conservative so failed runs do not hide potentially useful intermediate audio.
- Keep the implementation local to pipeline orchestration.

**Non-Goals:**

- Add a new cleanup CLI flag or configurable retention policy.
- Change standalone transcription provider behavior.
- Delete raw SRT files, improved SRT files, or user-provided media files.

## Decisions

- Delete audio in `run_pipeline` immediately after the transcription stage succeeds. This keeps cleanup close to the lifecycle owner and ensures the raw SRT has been created before deletion. Alternative considered: delete audio in `extract_audio`, but that stage cannot know when downstream transcription has safely consumed the file.
- Do not delete audio when extraction or transcription fails. This avoids making failed runs harder to diagnose and avoids removing files when the pipeline has not achieved the requested raw SRT output. Alternative considered: use a `finally` block to always clean up, but that would remove evidence from failed runs.
- Treat missing audio at cleanup time as non-fatal if it has already disappeared. The pipeline's user-facing result is the SRT artifact; cleanup should not fail a successful transcription because the transient file was removed externally. Alternative considered: fail on cleanup errors, but that makes an auxiliary cleanup step affect successful output creation.

## Risks / Trade-offs

- [Risk] Users relying on cached extracted MP3 files will lose that implicit cache after successful runs. Mitigation: document this as a breaking change in the proposal and update the orchestrator requirement.
- [Risk] File deletion can raise filesystem errors after a valid raw SRT exists. Mitigation: handle benign missing-file cleanup separately and surface unexpected deletion errors only if they indicate the filesystem operation failed.
- [Risk] Improved subtitle runs still need the raw SRT after audio deletion. Mitigation: delete only the audio path and leave raw SRT lifecycle unchanged.
