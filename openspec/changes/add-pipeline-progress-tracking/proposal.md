## Why

Long-running transcription pipeline runs currently provide only coarse stage start/completion feedback, which makes it hard for users to tell whether a run is still making progress or where time is being spent. This change improves observability during a single pipeline run without requiring external tooling or interactive prompts.

## What Changes

- Add structured progress updates for pipeline stages so users can follow the current stage, total stage count, and status transitions.
- Include enough context in progress output to identify the provider/model and relevant input/output artifacts during long runs.
- Preserve stderr as the progress channel so generated SRT content and stdout remain script-friendly.
- Ensure failures report the failed stage and stop subsequent progress reporting for later stages.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `pipeline-orchestrator`: expand progress reporting requirements from basic per-stage lines to structured, followable pipeline progress across stage start, completion, and failure.

## Impact

- Affects the pipeline orchestrator CLI/runtime behavior.
- Affects tests or fixtures that assert stderr output.
- No new external dependencies are expected.
- No breaking changes to generated files or provider selection APIs.
