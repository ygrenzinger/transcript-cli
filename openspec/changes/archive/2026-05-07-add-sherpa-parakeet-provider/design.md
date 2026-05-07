## Context

The current pipeline has a stable provider interface in `python/providers.py`: each provider validates its required configuration, resolves a provider-scoped model, transcribes an audio file, and atomically writes raw SRT cues. The orchestrator in `python/transcribe.py` selects the provider, extracts an MP3, invokes transcription through the shared interface, and names artifacts using the provider name.

Existing providers are cloud-backed and validate credentials or project configuration before transcription. `sherpa-parakeet` is different: it is a local provider whose readiness depends on installed runtime support, cached model assets, audio conversion, and available execution providers rather than remote credentials.

## Goals / Non-Goals

**Goals:**

- Add `sherpa-parakeet` as a first-class provider without adding sherpa-specific logic to the orchestrator.
- Automatically download and cache the sherpa-onnx Parakeet V3 int8 model on first use.
- Prefer an available accelerator runtime where sherpa-onnx supports it, while reliably falling back to CPU.
- Convert provider output into raw SRT using the same atomic output behavior as existing providers.
- Keep global `--language` compatibility by accepting the argument but ignoring it for this auto-detecting provider.

**Non-Goals:**

- No generic model manager beyond the assets required by Parakeet V3.
- No interactive download prompts.
- No speaker diarization support.
- No changes to audio extraction output format for other providers.
- No guarantee that accelerator execution is used on every machine; CPU fallback is acceptable.

## Decisions

### Provider name and model identity

Register the provider as `sherpa-parakeet` and expose one model key, `parakeet-tdt-0.6b-v3-int8`, mapped to the sherpa-onnx converted model `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`.

Alternatives considered:

- `parakeet`: shorter, but hides the runtime choice and could collide with future non-sherpa Parakeet integrations.
- Full sherpa model name as the CLI model: precise, but too verbose for normal use.

### Cache model assets on demand

The provider should ensure the required model files exist before transcription: `encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, and `tokens.txt`. If any are missing, it should download the published tarball, extract it into a cache directory, and then validate the expected files.

The default cache location should be user-scoped and outside the repository. An environment override can be supported for deterministic tests and explicit user control.

Alternatives considered:

- Require pre-downloaded files: simpler implementation, worse one-command UX.
- Commit model files to the repo: not viable due to size and third-party artifact management.

### Keep audio conversion provider-local

The orchestrator should continue extracting MP3. `sherpa-parakeet` should perform any required conversion to single-channel WAV/PCM in a temporary provider-owned file before invoking sherpa-onnx.

This preserves existing behavior for cloud providers and keeps sherpa-specific format constraints behind the provider boundary.

### Runtime provider selection

The provider should try an accelerator-backed sherpa-onnx execution provider where available, then fall back to CPU. Runtime selection must be non-fatal unless no runtime can transcribe successfully.

The implementation should make the selected runtime observable through progress, debug logs, or provider tests where practical, but the orchestrator should not know about runtime details.

Alternatives considered:

- CPU-only first: simpler and predictable, but leaves performance on the table on Apple Silicon or GPU-capable machines.
- User-required runtime flag: more control, but higher setup burden and worse default UX.

### Ignore language hints

The global `--language` option remains accepted for all providers. `sherpa-parakeet` ignores it because Parakeet V3 auto-detects supported languages. Documentation should state this explicitly.

## Risks / Trade-offs

- Download size and first-run latency -> cache model assets and show clear failure messages when download or extraction fails.
- Runtime availability varies by platform -> attempt acceleration opportunistically and fall back to CPU.
- Long recordings may need segmentation for stable memory usage -> prefer sherpa-onnx VAD/offline long-audio flow if the Python API supports it cleanly; otherwise use a documented subprocess strategy.
- sherpa-onnx output shape may differ between API and CLI paths -> isolate parsing in provider helpers and cover with unit tests.
- MP3-to-WAV conversion can add another dependency or require ffmpeg availability -> keep conversion local to the provider and fail with a clear provider error if conversion support is unavailable.

## Migration Plan

No data migration is required. Existing provider names, models, and output files remain unchanged. Users can opt into the new provider with `--provider sherpa-parakeet`; existing default behavior remains `voxtral` unless changed separately.

Rollback is removing the provider registration and dependency/documentation additions. Cached model files are user-local runtime artifacts and do not affect repository state.

## Open Questions

- Exact cache environment variable names should be finalized during implementation.
- The implementation should confirm whether the sherpa-onnx Python API exposes the desired VAD/segment timestamps cleanly enough; otherwise the CLI wrapper path is acceptable.
