## Context

The current pipeline orchestrator lives in `python/pipeline.py` and emits plain stderr messages before and after the four high-level stages. That satisfies basic visibility, but the format is inconsistent and does not clearly associate every event with a status, provider/model context, or failure point.

The pipeline remains a single-command CLI that writes generated artifacts to files and uses stderr for operational messages. Progress reporting must not require an interactive terminal, a separate monitoring process, or changes to provider implementations.

## Goals / Non-Goals

**Goals:**

- Provide predictable progress events for each pipeline stage: start, completion, and failure.
- Keep progress output on stderr so stdout remains available for scripting.
- Include stage index, total stages, stage name, status, and useful context such as provider/model or artifact path.
- Keep the implementation local to the orchestrator unless a stage later exposes more granular progress callbacks.

**Non-Goals:**

- Add real-time provider-level transcription percentages or ETA calculations.
- Introduce a TUI, progress bar dependency, daemon, or external telemetry sink.
- Change provider APIs, SRT output format, or artifact naming.

## Decisions

- Use structured, line-oriented stderr messages instead of terminal control sequences. This keeps output readable in terminals, logs, and CI, and avoids adding dependencies for progress bars.
- Centralize progress emission in the orchestrator around a small stage runner. Wrapping each stage call gives consistent start/done/fail reporting and preserves the existing stop-on-failure behavior.
- Treat the current four pipeline stages as the progress unit. The transcription provider may be long-running internally, but provider APIs do not currently expose incremental progress, so the orchestrator should avoid inventing misleading percentages.
- Include status words in every progress line (`START`, `DONE`, `FAIL`) while preserving human-readable text. This gives users readable output and makes tests assert stable markers rather than fragile prose.

## Risks / Trade-offs

- More stderr output could affect tests that compare exact messages -> update tests to assert required progress markers and failure context instead of complete stderr equality.
- Users may still want finer-grained transcription progress inside provider calls -> document that the first implementation tracks orchestrator stage progress only, with provider-level progress left for future provider API changes.
- Wrapping stages could accidentally mask original exceptions -> re-raise original exceptions after emitting failure progress so existing error handling and exit status behavior remains unchanged.
