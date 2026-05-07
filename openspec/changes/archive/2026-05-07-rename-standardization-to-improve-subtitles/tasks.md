## 1. Rename Subtitle Improvement Capability

- [x] 1.1 Rename the implementation module, public functions, CLI descriptions, and progress labels from `standardize_srt`/standardization terminology to subtitle improvement terminology.
- [x] 1.2 Preserve the existing cleanup behavior for cue filtering, splitting, wrapping, reading speed, gap enforcement, speaker handling, re-indexing, and validation under the new subtitle-improvement names.
- [x] 1.3 Update package entry metadata and direct script usage so the renamed subtitle-improvement module remains runnable with `uv run`.

## 2. Pipeline Behavior And Artifacts

- [x] 2.1 Change the pipeline to always write raw provider output as `<video>.<provider>.raw.srt` and return/report that raw artifact when improvement is not enabled.
- [x] 2.2 Add an explicit non-interactive option to enable subtitle improvement in the pipeline.
- [x] 2.3 When subtitle improvement is enabled, write improved output to `<video>.<provider>.improved.srt` by default and validate that improved file before success.
- [x] 2.4 Update `--output` handling so custom output paths apply only to explicitly requested improved subtitle output, or document and enforce the chosen behavior consistently.
- [x] 2.5 Make progress stage counts and stage names reflect the actually executed stages for raw-only and improved runs.

## 3. Specs And Documentation

- [x] 3.1 Update README usage, output descriptions, and examples to describe raw-only default output and optional improved output.
- [x] 3.2 Replace stale `standardize`, `standardization`, and `standardized` references in code comments, docs, progress messages, and OpenSpec text where they refer to the renamed capability.
- [x] 3.3 Ensure the new `subtitle-improvement` spec and modified pipeline spec validate with OpenSpec.

## 4. Verification

- [x] 4.1 Run the subtitle-improvement script against a raw SRT containing a zero-duration cue and verify the improved output validates.
- [x] 4.2 Run or add automated tests for raw-only pipeline output naming and optional improved output naming.
- [x] 4.3 Run the project validation commands, including `openspec validate rename-standardization-to-improve-subtitles --strict`.
