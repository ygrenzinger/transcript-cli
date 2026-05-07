## ADDED Requirements

### Requirement: Sherpa Parakeet provider
The capability SHALL provide a registered transcription provider named `sherpa-parakeet` backed by sherpa-onnx and the converted Parakeet V3 int8 model. The provider SHALL convert sherpa-onnx recognition output into raw SRT output at the caller-specified path without requiring cloud credentials.

#### Scenario: Sherpa Parakeet successful transcription
- **GIVEN** an MP3 audio file with intelligible speech
- **WHEN** the caller invokes transcription with `--provider sherpa-parakeet`
- **THEN** the Sherpa Parakeet provider writes an SRT file to the caller-specified output path
- **AND** the command exits with a zero status

#### Scenario: Sherpa Parakeet is discoverable
- **GIVEN** the provider registry is queried
- **WHEN** providers and models are listed
- **THEN** the output includes provider `sherpa-parakeet`
- **AND** the output lists `parakeet-tdt-0.6b-v3-int8` as its default and supported model

### Requirement: Sherpa Parakeet model cache
The `sherpa-parakeet` provider SHALL download and cache the required sherpa-onnx Parakeet V3 model assets on first use. The provider SHALL reuse valid cached assets on subsequent runs and SHALL fail with a clear provider error if required model assets cannot be downloaded, extracted, or validated.

#### Scenario: First use downloads model assets
- **GIVEN** the required Parakeet V3 model assets are absent from the configured cache
- **WHEN** the caller invokes transcription with `--provider sherpa-parakeet`
- **THEN** the provider downloads and extracts the required model assets before recognition starts
- **AND** transcription proceeds using the cached assets

#### Scenario: Cached assets are reused
- **GIVEN** valid Parakeet V3 model assets already exist in the configured cache
- **WHEN** the caller invokes transcription with `--provider sherpa-parakeet`
- **THEN** the provider uses the cached assets without downloading them again

#### Scenario: Model cache failure is clear
- **GIVEN** required Parakeet V3 model assets are absent and download or extraction fails
- **WHEN** the caller invokes transcription with `--provider sherpa-parakeet`
- **THEN** the command exits with a non-zero status
- **AND** the error message clearly identifies the model cache failure
- **AND** no partial SRT file is written

### Requirement: Sherpa Parakeet runtime fallback
The `sherpa-parakeet` provider SHALL prefer an available accelerator runtime supported by sherpa-onnx, such as CoreML or GPU execution where available, and SHALL fall back to CPU when acceleration is unavailable or unsupported.

#### Scenario: Accelerator runtime is available
- **GIVEN** the local environment supports a sherpa-onnx accelerator runtime
- **WHEN** the caller invokes transcription with `--provider sherpa-parakeet`
- **THEN** the provider attempts recognition using the accelerator runtime before CPU

#### Scenario: CPU fallback when accelerator is unavailable
- **GIVEN** no supported sherpa-onnx accelerator runtime is available
- **WHEN** the caller invokes transcription with `--provider sherpa-parakeet`
- **THEN** the provider falls back to CPU recognition
- **AND** the run can still complete successfully

### Requirement: Sherpa Parakeet language handling
The `sherpa-parakeet` provider SHALL ignore the global language hint because Parakeet V3 auto-detects supported languages. Passing `--language` with `--provider sherpa-parakeet` SHALL NOT be treated as an error.

#### Scenario: Language hint ignored
- **GIVEN** provider `sherpa-parakeet` is selected
- **WHEN** the caller invokes transcription with `--language fr`
- **THEN** the provider does not pass a fixed language to sherpa-onnx
- **AND** the transcription attempt proceeds using Parakeet V3 auto-detection

### Requirement: Sherpa Parakeet audio preparation
The `sherpa-parakeet` provider SHALL prepare the caller-supplied audio in the format required by sherpa-onnx while keeping conversion details inside the provider boundary. Temporary conversion artifacts SHALL be removed after successful provider execution.

#### Scenario: MP3 input converted for sherpa-onnx
- **GIVEN** the caller supplies an MP3 audio file produced by the pipeline extractor
- **WHEN** provider `sherpa-parakeet` performs transcription
- **THEN** it prepares audio in a sherpa-onnx-compatible format before recognition
- **AND** it writes raw SRT output through the shared provider interface

#### Scenario: Conversion failure is a provider error
- **GIVEN** the supplied audio cannot be converted into a sherpa-onnx-compatible format
- **WHEN** provider `sherpa-parakeet` performs transcription
- **THEN** the command exits with a non-zero status
- **AND** the error message clearly identifies the audio preparation failure
- **AND** no partial SRT file is written
