## Why

Long audio files can exceed practical limits for some transcription providers and can produce lower-quality results when processed as one uninterrupted request. A shared, configurable splitter lets the pipeline prepare provider-friendly audio chunks while keeping chunking behavior consistent across providers.

## What Changes

- Add an FFmpeg-based audio splitting capability that can split long audio into shorter chunks.
- Allow splitting behavior to be configured, including target chunk duration, overlap duration, silence detection threshold, minimum silence duration, and search window.
- Prefer natural silence points near target boundaries, with a deterministic fallback to time-based splitting when no suitable silence is found.
- Preserve overlap metadata so downstream transcription results can be merged without losing speech around split boundaries.
- Add merged SRT output behavior for provider workflows that process split chunks internally.
- Keep splitting out of the pipeline and CLI; each provider decides whether it needs chunking while preserving the existing provider contract.
- Configure default provider policies so Grok and Voxtral/Mistral do not chunk, Vertex Gemini chunks at 15 minutes, and Sherpa Parakeet V3 chunks at 120 seconds with 15 seconds of overlap.

## Capabilities

### New Capabilities
- `audio-splitting`: Defines reusable configurable FFmpeg-backed audio chunking, silence-aware split point selection, chunk metadata, and overlap-safe merge behavior for providers.

### Modified Capabilities
- `audio-to-srt-transcription`: Providers may use chunked transcription internally, while retaining the same caller-facing contract of producing one SRT file.
- `pipeline-orchestrator`: The orchestrator must continue invoking the selected provider once and must not expose splitter controls or implement provider chunking itself.

## Impact

- Affected code: audio preparation utilities, transcription provider invocation flow, SRT merging utilities, pipeline orchestration, CLI/configuration handling, and tests.
- External dependencies: uses existing FFmpeg tooling (`ffmpeg` and `ffprobe`) rather than adding a new media dependency.
- APIs: provider implementations remain responsible for accepting one supplied audio path and writing one SRT; providers that need chunking use the shared splitter internally.
- Systems: long-running transcription jobs gain more predictable chunk sizes, clearer intermediate artifacts, and safer handling around chunk boundaries.
