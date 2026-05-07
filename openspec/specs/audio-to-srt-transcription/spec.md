# audio-to-srt-transcription Specification

## Purpose
Transform an audio file into an SRT subtitle file. This capability defines a **provider interface** so that multiple transcription backends (e.g. Mistral Voxtral, xAI Grok) can be plugged in interchangeably. Providers are responsible for the speech-to-text step and for emitting cues in SRT form. The canonical shared output structure across all providers is the SRT file itself (not a provider-specific structured payload). Concerns related to enforcing readability best-practices live in the `srt-standardization` capability; correctness checks live in `srt-validation`.
## Requirements
### Requirement: Provider contract
A transcription provider SHALL implement a single operation: given an audio file path and an optional language hint, produce an SRT file at a caller-specified path.

#### Scenario: Successful transcription
- GIVEN an MP3 audio file with intelligible speech
- WHEN a registered provider is invoked with that file path
- THEN it writes an SRT file to the caller-specified output path
- AND it exits with a zero status

#### Scenario: Provider failure
- GIVEN the underlying STT API returns an error (e.g. invalid credentials, network failure, unsupported audio)
- WHEN the provider is invoked
- THEN it exits with a non-zero status and a clear error message
- AND it does not write a partial SRT file

### Requirement: Transient provider retry
The transcription capability SHALL automatically retry transient provider call failures before returning a final provider error. Retry behavior SHALL be always enabled, SHALL apply to all registered transcription providers invoked through the shared provider interface, and SHALL be used by both the full video pipeline and the standalone transcription command. The capability SHALL retry up to 3 times after the initial attempt, using default backoff delays of 1s, 2s, and 4s. For Grok HTTP 429 responses that include `Retry-After`, the capability SHALL use the provider-supplied retry delay for that retry attempt instead of the default backoff delay.

#### Scenario: Transient failure succeeds after retry
- GIVEN a registered transcription provider fails a transcription attempt with a transient provider call failure
- WHEN a later retry attempt succeeds
- THEN the transcription command writes the requested SRT output
- AND the command exits with a zero status

#### Scenario: Retry exhaustion returns clear error
- GIVEN a registered transcription provider continues to fail with transient provider call failures
- WHEN the initial attempt and 3 retry attempts have all failed
- THEN the transcription command exits with a non-zero status
- AND the final error message clearly identifies the provider transcription failure
- AND no partial SRT file is written

#### Scenario: Non-transient failure is not retried
- GIVEN a registered transcription provider fails because of a non-transient condition such as missing credentials, unsupported model, malformed successful response, or empty transcription result
- WHEN the provider failure is handled
- THEN the transcription command exits with a non-zero status without exhausting retry attempts
- AND the error message describes the non-transient failure

#### Scenario: Grok rate limit respects Retry-After
- GIVEN the Grok provider receives an HTTP 429 response with a `Retry-After` value
- WHEN the retry delay is selected for that failed attempt
- THEN the retry waits according to the `Retry-After` value instead of the default exponential backoff delay

#### Scenario: Retry applies to full pipeline and standalone command
- GIVEN a transient provider call failure occurs during transcription
- WHEN transcription is invoked through either `video-to-srt` or `transcribe-srt`
- THEN the same retry policy is applied before the command reports final success or failure

### Requirement: Pluggable provider selection
The capability SHALL allow the caller to select a provider by name at invocation time. New providers SHALL be addable without modifying existing providers or the orchestrator's core logic.

#### Scenario: Provider switch
- GIVEN providers `voxtral`, `grok`, and `vertex-gemini` are registered
- WHEN the caller specifies `--provider grok` (or equivalent)
- THEN the Grok-backed implementation is used to produce the SRT
- AND switching to `--provider voxtral` for the same audio uses the Voxtral-backed implementation instead
- AND switching to `--provider vertex-gemini` uses the Vertex Gemini-backed implementation instead

#### Scenario: Unknown provider
- GIVEN a provider name that is not registered
- WHEN the caller selects it
- THEN the capability exits with a non-zero status and lists the available providers in its error message

### Requirement: Provider-scoped model selection
The capability SHALL accept a global `--model` argument (or equivalent) at invocation time. The model value is interpreted within the selected provider's model namespace. The `voxtral` provider SHALL expose exactly one supported model: `voxtral-mini-2602`. The `vertex-gemini` provider SHALL expose `gemini-2.5-flash` and `gemini-2.5-pro`, and SHALL use `gemini-2.5-flash` by default.

#### Scenario: Supported model for selected provider
- GIVEN provider `grok` is selected and model `grok-transcribe-1` is supported by `grok`
- WHEN the caller invokes the capability with `--provider grok --model grok-transcribe-1`
- THEN the `grok` provider uses that model to perform transcription

#### Scenario: Default Voxtral model
- GIVEN provider `voxtral` is selected
- WHEN the caller invokes the capability without `--model`
- THEN the `voxtral` provider uses `voxtral-mini-2602`

#### Scenario: Explicit Voxtral model
- GIVEN provider `voxtral` is selected
- WHEN the caller invokes the capability with `--provider voxtral --model voxtral-mini-2602`
- THEN the `voxtral` provider uses `voxtral-mini-2602`

#### Scenario: Default Vertex Gemini model
- GIVEN provider `vertex-gemini` is selected
- WHEN the caller invokes the capability without `--model`
- THEN the `vertex-gemini` provider uses `gemini-2.5-flash`

#### Scenario: Explicit Vertex Gemini model
- GIVEN provider `vertex-gemini` is selected
- WHEN the caller invokes the capability with `--provider vertex-gemini --model gemini-2.5-flash`
- THEN the `vertex-gemini` provider uses `gemini-2.5-flash`

#### Scenario: Explicit Vertex Gemini Pro model
- GIVEN provider `vertex-gemini` is selected
- WHEN the caller invokes the capability with `--provider vertex-gemini --model gemini-2.5-pro`
- THEN the `vertex-gemini` provider uses `gemini-2.5-pro`

#### Scenario: Unsupported model for selected provider
- GIVEN provider `voxtral` is selected and model `grok-transcribe-1` is not supported by `voxtral`
- WHEN the caller invokes the capability with `--provider voxtral --model grok-transcribe-1`
- THEN the capability exits with a non-zero status (fail fast)
- AND it returns a clear error that the model is unsupported for that provider
- AND it does not start a transcription attempt

### Requirement: Provider and model discoverability
The capability SHALL expose a discoverability command (or equivalent API) that lists registered providers and the models supported by each provider.

#### Scenario: List providers and models
- GIVEN `voxtral`, `grok`, and `vertex-gemini` providers are registered with distinct model sets
- WHEN the caller invokes the discoverability command
- THEN the output includes each provider name
- AND the output lists the supported models for each provider in a machine-readable or clearly parseable form
- AND the `vertex-gemini` entry lists `gemini-2.5-flash` as its default model
- AND the `vertex-gemini` entry lists `gemini-2.5-flash` and `gemini-2.5-pro` as supported models

### Requirement: Word-level timing fidelity
Each provider SHALL produce SRT cues whose timestamps reflect the best timing information available from the underlying provider. Providers that receive native word or segment timing metadata from a dedicated speech-to-text API SHALL preserve that timing with millisecond precision. Providers that do not receive native timing metadata MAY emit model-derived segment timestamps, provided those timestamps are ordered, valid for SRT output, and documented as approximate.

#### Scenario: Cue timing reflects native speech timing
- GIVEN a dedicated speech-to-text provider returns native timing where the words "hello world" are spoken from 1.250 s to 2.480 s
- WHEN the provider emits the corresponding cue
- THEN the cue's start and end timestamps match those bounds within ±50 ms

#### Scenario: Model-derived timing is accepted for Vertex Gemini
- GIVEN provider `vertex-gemini` returns model-derived segment timestamps without native word or segment timing metadata
- WHEN the provider emits SRT cues
- THEN the cues have ordered start and end timestamps with positive duration
- AND the provider documentation identifies those timestamps as approximate

### Requirement: Language hint
The capability SHALL accept an optional language code (e.g. `en`, `fr`) and forward it to the provider when supplied. Providers MAY use it to improve accuracy.

#### Scenario: Language hint provided
- GIVEN the caller passes `--language fr`
- WHEN the provider is invoked
- THEN it forwards the hint to its underlying STT API in the form that API expects

#### Scenario: No language hint
- GIVEN no language is specified
- WHEN the provider is invoked
- THEN it relies on the underlying API's auto-detection (or default), without erroring

### Requirement: Provider boundary
A provider SHALL NOT be responsible for enforcing readability best-practices (cps, line length, inter-cue gap). Its output is treated as raw transcription cues that the orchestrator will pass through `srt-validation` and `srt-standardization`.

#### Scenario: Raw provider output may exceed best-practice limits
- GIVEN a provider emits a cue whose text exceeds 84 characters or whose duration exceeds 7 s
- WHEN the orchestrator receives this cue
- THEN it is the orchestrator's responsibility (via the standardization step) to reshape such cues — the provider is not faulted for them

### Requirement: Provider configuration requirements
A transcription provider SHALL declare all required configuration values that can be validated before transcription starts. The capability SHALL fail fast with a clear error naming missing required configuration values before invoking the provider.

#### Scenario: Provider has multiple required configuration values
- **GIVEN** provider `vertex-gemini` requires `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`
- **WHEN** either required value is missing
- **THEN** the capability exits with a non-zero status before starting transcription
- **AND** the error message names the missing required configuration value

#### Scenario: Existing API key providers keep single required value behavior
- **GIVEN** provider `grok` requires `XAI_API_KEY`
- **WHEN** `XAI_API_KEY` is missing
- **THEN** the capability exits with a non-zero status before starting transcription
- **AND** the error message names `XAI_API_KEY`

### Requirement: Vertex Gemini provider
The capability SHALL provide a registered transcription provider named `vertex-gemini` backed by Google Vertex AI Gemini. The provider SHALL use Google Application Default Credentials, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION` to call Vertex AI, and SHALL convert the model response into raw SRT output at the caller-specified path.

#### Scenario: Vertex Gemini successful transcription
- **GIVEN** an MP3 audio file with intelligible speech and valid Vertex AI configuration
- **WHEN** the caller invokes transcription with `--provider vertex-gemini`
- **THEN** the Vertex Gemini-backed provider writes an SRT file to the caller-specified output path
- **AND** the command exits with a zero status

#### Scenario: Vertex Gemini malformed response
- **GIVEN** the Vertex Gemini API returns a response that cannot be parsed into timestamped subtitle segments
- **WHEN** the provider handles the response
- **THEN** the capability exits with a non-zero status and a clear provider error
- **AND** it does not write a partial SRT file

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
