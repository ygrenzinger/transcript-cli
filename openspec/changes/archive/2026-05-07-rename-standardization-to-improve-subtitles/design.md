## Context

The current pipeline extracts audio, transcribes to `<video>.<provider>.raw.srt`, and then always runs `standardize_srt` to produce a final `.srt`. The naming implies mandatory normalization rather than optional post-processing, and the final `.srt` path hides which provider produced the source transcription.

The existing cleanup logic is still useful: it filters invalid provider cues, splits long cues, wraps lines, enforces reading speed and gaps, handles speaker labels, re-indexes, and validates the result. This change keeps that behavior but reframes it as an optional improvement step with explicit artifact naming.

## Goals / Non-Goals

**Goals:**

- Rename the user-facing and spec-facing capability from SRT standardization to subtitle improvement.
- Preserve raw transcription output at `<video>.<provider>.raw.srt`.
- Produce improved subtitles at `<video>.<provider>.improved.srt` when the improvement step is enabled.
- Make the improvement stage optional in the pipeline while keeping validation for generated improved output.
- Keep the current readability-improvement rules functionally equivalent unless the specs explicitly change them.

**Non-Goals:**

- Rewriting the subtitle cleanup algorithms.
- Adding new transcription providers.
- Changing provider raw SRT generation semantics.
- Introducing a second subtitle file format beyond SRT.

## Decisions

1. Use `subtitle-improvement` as the new capability name.

The term describes the behavior without implying that raw provider SRT must already satisfy every readability rule. Alternative considered: keep `srt-standardization` and add an optional flag, but that keeps the misleading mandatory-standardization language.

2. Keep raw provider SRT as the required pipeline artifact.

The raw artifact is the authoritative provider output and is useful for debugging, comparison, and rerunning improvement without retranscription. Alternative considered: overwrite raw output with improved output, but that would remove provenance and make provider issues harder to inspect.

3. Use `<video>.<provider>.improved.srt` for improved output.

Including the provider avoids collisions when multiple providers transcribe the same video. Alternative considered: `<video>.improved.srt`, but that loses provider identity and can be overwritten by later runs.

4. Make subtitle improvement opt-in from the pipeline CLI.

The default pipeline should be able to stop after raw transcription, while users can request improved subtitles when they want readability cleanup. The implementation should expose a clear CLI flag rather than relying on implicit output naming.

5. Keep the existing implementation initially, then rename around it.

Implementation can preserve the current cleanup functions while moving public names, scripts, progress labels, documentation, and specs to `improve_subtitles` terminology. This limits behavioral risk while removing the confusing standardization concept.

## Risks / Trade-offs

- Existing commands expecting a final `<video>.srt` may break. Mitigation: document the new raw and improved output paths clearly and preserve `--output` only for explicitly requested improved output if kept.
- Optional improvement can leave users with only raw provider output by default. Mitigation: progress output and final messages should explicitly report the artifact path written.
- Renaming files and functions may leave stale references. Mitigation: search for `standardize`, `standardization`, and `standardized` across code, docs, and specs during implementation.
- Archiving or superseding `srt-standardization` may require careful OpenSpec handling. Mitigation: provide a new `subtitle-improvement` spec and a delta that removes or redirects old terminology as part of this change.
