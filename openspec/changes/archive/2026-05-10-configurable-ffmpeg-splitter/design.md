## Context

The Python pipeline currently extracts one MP3 from a video, sends that single audio file to the selected transcription provider, and writes one raw SRT file. Providers expose a shared `transcribe(audio_path, output_path, model, language)` interface and the orchestrator is responsible for stage ordering, progress reporting, and intermediate artifact cleanup.

Some providers and models are more reliable when audio is shorter, but the pipeline should not expose that implementation detail. The splitter should therefore be a shared provider utility: providers can opt into it behind their `transcribe(audio_path, output_path, model, language)` contract, while the pipeline still calls the selected provider once.

## Goals / Non-Goals

**Goals:**

- Provide a configurable FFmpeg-backed splitter for audio files that can be reused by multiple providers.
- Split near natural silence where possible, while keeping deterministic behavior when silence detection does not find a suitable boundary.
- Preserve enough chunk metadata to translate provider-local SRT timestamps back onto the original audio timeline.
- Merge chunk SRT outputs into one raw SRT file and remove duplicated overlap cues.
- Keep the pipeline focused on extracting audio, invoking the selected provider once, and optionally improving subtitles.
- Let providers declare and own their split policy without adding splitter parameters to the user-facing tool.

**Non-Goals:**

- Replacing FFmpeg audio extraction.
- Changing provider-specific API calls or authentication requirements.
- Improving subtitle readability; that remains the subtitle improvement stage.
- Performing diarization, translation, or audio enhancement.
- Guaranteeing perfect semantic deduplication for every provider output shape.

## Decisions

### Shared splitter module outside providers

Create reusable splitter modules containing the splitter configuration, chunk metadata, FFmpeg command execution, silence parsing, and SRT merge helpers.

Rationale: this keeps chunking reusable while still allowing providers to own the decision to chunk or not chunk.

Alternatives considered: implement splitting inside each provider. That would duplicate command construction, temporary-file handling, and timestamp correction, and would make provider behavior diverge over time.

### Preserve the provider and pipeline contracts

The provider interface remains `transcribe(audio_path, output_path, model, language) -> None`. The pipeline invokes the selected provider once. Providers that need chunking call an internal single-chunk transcription function for each chunk and merge the resulting per-chunk SRT files into the final caller-requested raw SRT path.

Rationale: whether a provider needs chunking depends on provider limits and behavior. The pipeline should not know or expose that concern.

Alternatives considered: add pipeline-level splitter flags or a new bulk-transcription provider method. Pipeline flags leak provider internals to users, and a bulk method would require every provider to understand chunk lists even when the provider has no special chunking need.

### Use silence-aware split points with time-based fallback

The splitter uses `ffprobe` to read duration and `ffmpeg -af silencedetect` to find candidate pauses. For each target boundary, it searches within a configurable window, chooses a silence based on closeness and duration, and falls back to the target timestamp when no candidate is found.

Rationale: natural split points reduce the chance of cutting words, but the operation must complete predictably even on continuous speech or music.

Alternatives considered: always split by fixed duration. That is simpler but more likely to cut speech. Full speech-aware segmentation was rejected as heavier than needed and outside current dependencies.

### Overlap and merge through SRT cues

Chunks include configurable overlap at internal boundaries. After each chunk is transcribed, parsed SRT cues are offset by the chunk's original start time and merged. Cues in overlap windows are deduplicated using normalized text similarity first, then a timestamp cutoff fallback.

Rationale: overlap prevents lost speech near boundaries, and SRT cues are the canonical shared provider output in this project.

Alternatives considered: merge provider-native segment JSON. That would couple the merger to provider-specific response formats and conflict with the existing SRT contract.

### Temporary artifact lifecycle belongs to orchestration

The splitter writes chunks and per-chunk SRT files under a temporary work directory by default. Successful runs remove these intermediates and keep only the final raw SRT. Failed runs should preserve enough context to diagnose unless the existing cleanup conventions clearly prefer removal.

Rationale: the current pipeline removes extracted audio after successful transcription but keeps it on failure. Chunk artifacts should follow the same diagnostic-friendly pattern.

Alternatives considered: write chunks next to the source media. That risks clutter, name collisions, and accidental reuse across incompatible splitter settings.

### Configuration is provider-owned

Add provider-owned configuration fields for enabling splitting, target chunk duration, overlap duration, silence threshold, minimum silence duration, and search window. These fields are not CLI or pipeline options.

Default provider policies are: no chunking for Grok, no chunking for Voxtral/Mistral, 900-second chunks for Vertex Gemini, and 120-second chunks with 15-second overlap for Sherpa Parakeet V3.

Rationale: provider defaults avoid invalid user choices such as enabling splitting for providers that do not need it or disabling it for providers that require it.

Alternatives considered: always split all audio or expose a top-level `--split-audio` option. Both add user-facing complexity and make the pipeline responsible for provider limits.

## Risks / Trade-offs

- Text similarity may fail to identify duplicate overlap cues when providers phrase the same audio differently -> fall back to time-window trimming and keep thresholds configurable.
- Codec-copy chunk extraction may produce chunks with inaccurate boundaries for some containers -> use FFmpeg seeking consistently and allow re-encoding if tests reveal boundary issues.
- More provider calls can increase cost and runtime -> only providers with a declared split policy use chunking.
- Per-chunk retry can partially succeed before a later chunk fails -> write the final SRT atomically only after every chunk succeeds.
- Silence detection thresholds may not fit every recording -> expose threshold and duration configuration rather than hard-coding one profile.
- Temporary chunks may consume disk for very long media -> use a temporary directory and clean up after successful completion.

## Migration Plan

1. Add splitter and merger utilities with unit tests that use generated or fixture audio where practical and pure SRT merge tests where media generation is unnecessary.
2. Add a chunked transcription helper that providers can call with their single-chunk transcription function and that writes one final SRT atomically.
3. Add provider split policy fields where needed; do not add CLI or pipeline splitter options.
4. Keep pipeline behavior unchanged: extract audio, call provider once, optionally improve subtitles.
5. Document that splitting is automatic for providers that declare a split policy.
6. Roll back by removing a provider's split policy; existing non-split provider flow remains intact.

## Open Questions

- Which production providers should declare a split policy by default remains a provider-specific operational decision.
