## Why

The pipeline currently treats subtitle readability cleanup as mandatory SRT standardization, which obscures the distinction between provider output and post-processed subtitles. Renaming this capability to optional subtitle improvement makes the raw provider artifact explicit and preserves a predictable improved artifact when cleanup is requested.

## What Changes

- Rename the `srt-standardization` concept, stage, and CLI-facing language to subtitle improvement.
- Make subtitle improvement optional in the pipeline instead of an unconditional post-transcription step.
- Preserve provider output as `<video>.<provider>.raw.srt`.
- Write improved subtitles to `<video>.<provider>.improved.srt` when improvement is enabled.
- Keep existing cleanup behavior for readability, cue filtering, splitting, wrapping, speaker handling, gap enforcement, and validation of improved output.
- **BREAKING**: The default pipeline output artifact naming changes from the current standardized `.srt` behavior to explicit raw and optional improved SRT artifacts.

## Capabilities

### New Capabilities
- `subtitle-improvement`: Optional post-processing of raw provider SRT into validated, readability-improved subtitles.

### Modified Capabilities
- `pipeline-orchestrator`: Pipeline stages and output artifact naming change to expose raw SRT and optional improved SRT outputs.
- `srt-standardization`: Existing standardization terminology and requirements are replaced by subtitle improvement.

## Impact

- Affected code: `python/standardize_srt.py`, `python/transcribe.py`, README/CLI documentation, and any references to the `standardize_srt` script or `standardize_srt` stage.
- Affected specs: `openspec/specs/srt-standardization/`, `openspec/specs/pipeline-orchestrator/`, and the new `subtitle-improvement` capability.
- No new third-party dependencies are expected.
