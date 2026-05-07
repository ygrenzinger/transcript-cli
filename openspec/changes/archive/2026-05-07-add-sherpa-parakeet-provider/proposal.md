## Why

The transcription pipeline currently relies on cloud-backed providers for high-quality speech recognition. Adding a local sherpa-onnx Parakeet V3 provider gives users an offline-capable option with strong multilingual ASR, native timing, and no API-key dependency.

## What Changes

- Register a new transcription provider named `sherpa-parakeet`.
- Support the sherpa-onnx converted Parakeet V3 model, exposed as `parakeet-tdt-0.6b-v3-int8`.
- Download and cache required sherpa-onnx model assets automatically on first use.
- Prefer an available accelerator runtime such as CoreML or GPU where supported, and fall back to CPU when acceleration is unavailable.
- Ignore the global `--language` hint for `sherpa-parakeet`, because Parakeet V3 auto-detects supported languages.
- Produce raw SRT output through the existing provider interface and file naming convention: `<video>.sherpa-parakeet.raw.srt`.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `audio-to-srt-transcription`: add the `sherpa-parakeet` provider contract, model/cache behavior, runtime fallback behavior, and language hint handling.
- `pipeline-orchestrator`: include `sherpa-parakeet` in provider/model selection and provider-specific output naming behavior without adding orchestrator-specific sherpa-onnx logic.

## Impact

- Affected code: `python/providers.py`, `python/transcribe.py` only if CLI discoverability or help text needs updates, `python/README.md`, and provider tests.
- Dependencies: add sherpa-onnx runtime support and any lightweight audio conversion/download helpers required by the implementation.
- Runtime artifacts: cached Parakeet V3 model files and temporary audio conversion files used by the provider.
- User-facing API: new `--provider sherpa-parakeet` option and provider-scoped `--model parakeet-tdt-0.6b-v3-int8`.
