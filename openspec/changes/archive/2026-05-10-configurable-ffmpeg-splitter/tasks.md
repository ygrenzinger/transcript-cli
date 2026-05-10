## 1. Splitter Core

- [x] 1.1 Add an `audio_splitter.py` module with splitter configuration, silence point metadata, chunk metadata, and explicit splitter error types.
- [x] 1.2 Implement ffprobe duration probing with clear failure messages for unreadable or unsupported audio.
- [x] 1.3 Implement FFmpeg silence detection parsing using configurable threshold and minimum silence duration.
- [x] 1.4 Implement split point selection that prefers silence inside the configured search window and falls back to target boundaries.
- [x] 1.5 Implement chunk extraction with overlap metadata, boundary clamping, ordered chunk output, and no-copy behavior for audio that does not need splitting.

## 2. SRT Merge

- [x] 2.1 Add cue timestamp offset helpers that convert chunk-local SRT cue times onto the original audio timeline.
- [x] 2.2 Implement overlap deduplication using normalized cue text similarity with a timing-based fallback.
- [x] 2.3 Implement merged SRT writing with chronological ordering and sequential cue reindexing.
- [x] 2.4 Ensure final merged SRT output is written atomically only after all chunk SRT inputs are available.

## 3. Transcription Integration

- [x] 3.1 Add a provider-owned chunked transcription helper that calls a provider's single-chunk transcription operation once per chunk.
- [x] 3.2 Pass the selected model and language hint unchanged to every chunk provider call.
- [x] 3.3 Apply existing provider retry behavior independently for each chunk.
- [x] 3.4 Stop chunked transcription on the first unrecoverable chunk failure and avoid writing a partial final SRT.

## 4. Provider Boundary And CLI

- [x] 4.1 Remove splitter options from the pipeline CLI and keep splitter configuration provider-owned.
- [x] 4.2 Validate provider-owned splitter option values before provider chunking starts.
- [x] 4.3 Keep the orchestrator flow as extract audio, invoke selected provider once, optionally improve subtitles.
- [x] 4.4 Preserve existing single-audio behavior for providers without a split policy.
- [x] 4.5 Preserve existing pipeline progress stage totals without exposing internal provider chunking stages.
- [x] 4.6 Let providers clean temporary chunk audio and per-chunk SRT artifacts after successful merged raw SRT creation while returning useful chunk failure context.

## 5. Tests And Documentation

- [x] 5.1 Add unit tests for split point selection, overlap boundary metadata, and no-split behavior.
- [x] 5.2 Add unit tests for SRT timestamp offsetting, cue reindexing, duplicate overlap removal, and time-cutoff fallback.
- [x] 5.3 Add provider-wrapper tests proving provider-owned chunked transcription preserves model/language, applies retries per chunk, and avoids partial final output on failure.
- [x] 5.4 Add orchestrator tests proving no splitter CLI/pipeline controls are exposed and progress totals remain unchanged.
- [x] 5.5 Update Python README usage documentation for provider-owned automatic audio splitting and artifact lifecycle.
- [x] 5.6 Run the relevant Python test suite and fix any failures introduced by the change.
