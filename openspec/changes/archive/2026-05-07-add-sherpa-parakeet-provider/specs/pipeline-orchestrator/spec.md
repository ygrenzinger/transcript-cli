## ADDED Requirements

### Requirement: Sherpa Parakeet pipeline selection
The orchestrator SHALL allow users to select the registered `sherpa-parakeet` transcription provider with the same provider/model selection mechanism used by other providers. The orchestrator SHALL invoke `sherpa-parakeet` only through the shared transcription provider interface and SHALL NOT contain sherpa-onnx-specific model, cache, runtime, or audio conversion logic.

#### Scenario: Run pipeline with Sherpa Parakeet
- **GIVEN** provider `sherpa-parakeet` is registered
- **WHEN** the user runs the pipeline with `--provider sherpa-parakeet`
- **THEN** the orchestrator invokes the Sherpa Parakeet-backed provider for the transcription stage
- **AND** the raw transcription output is written as `<video>.sherpa-parakeet.raw.srt`

#### Scenario: Explicit Sherpa Parakeet model
- **GIVEN** provider `sherpa-parakeet` is registered
- **WHEN** the user runs the pipeline with `--provider sherpa-parakeet --model parakeet-tdt-0.6b-v3-int8`
- **THEN** the orchestrator validates the provider-scoped model before running stages
- **AND** the Sherpa Parakeet provider uses `parakeet-tdt-0.6b-v3-int8`

#### Scenario: No orchestrator-specific Sherpa logic
- **GIVEN** provider `sherpa-parakeet` is registered by the transcription capability
- **WHEN** the user selects it via `--provider sherpa-parakeet`
- **THEN** the orchestrator invokes it through the shared provider interface
- **AND** the orchestrator does not contain sherpa-onnx-specific download, cache, runtime, model-file, or audio conversion logic
