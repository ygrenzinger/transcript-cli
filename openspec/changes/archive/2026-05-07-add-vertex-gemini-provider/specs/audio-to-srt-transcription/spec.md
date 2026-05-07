## ADDED Requirements

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

## MODIFIED Requirements

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
