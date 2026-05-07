## 1. Provider Registration

- [x] 1.1 Add a `sherpa-parakeet` provider implementation conforming to the existing `TranscriptionProvider` protocol.
- [x] 1.2 Register `sherpa-parakeet` in the provider registry with default model `parakeet-tdt-0.6b-v3-int8`.
- [x] 1.3 Ensure provider/model discoverability includes `sherpa-parakeet` and `parakeet-tdt-0.6b-v3-int8`.

## 2. Model Cache

- [x] 2.1 Add cache path resolution for Sherpa Parakeet model assets, including a testable environment override.
- [x] 2.2 Implement first-use download and extraction for `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`.
- [x] 2.3 Validate required cached files: `encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, and `tokens.txt`.
- [x] 2.4 Return clear provider errors for download, extraction, or cache validation failures without writing partial SRT output.

## 3. Recognition Runtime

- [x] 3.1 Add sherpa-onnx dependency/runtime integration using the smallest viable API surface.
- [x] 3.2 Implement accelerator-preferred runtime selection with CPU fallback.
- [x] 3.3 Keep runtime selection and sherpa-onnx details inside the provider boundary.

## 4. Audio And SRT Conversion

- [x] 4.1 Prepare MP3 input as sherpa-onnx-compatible audio in provider-owned temporary files.
- [x] 4.2 Convert sherpa-onnx recognition output into ordered positive-duration SRT cues.
- [x] 4.3 Ignore `--language` for `sherpa-parakeet` while allowing transcription to proceed.
- [x] 4.4 Remove temporary provider audio artifacts after successful transcription.

## 5. Documentation And Tests

- [x] 5.1 Document `--provider sherpa-parakeet`, model caching, language auto-detection, and CPU fallback behavior in `python/README.md`.
- [x] 5.2 Add unit tests for provider registration, model discoverability, cache validation, language ignoring, and cue conversion.
- [x] 5.3 Add tests or fakes covering accelerator fallback to CPU without requiring accelerator hardware.
- [x] 5.4 Run the provider and pipeline test suite.
