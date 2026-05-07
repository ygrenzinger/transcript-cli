## MODIFIED Requirements

### Requirement: Provider and model selection
The orchestrator SHALL expose a `--provider` option (or equivalent) to select between registered transcription providers (e.g. `voxtral`, `grok`, `vertex-gemini`) and a `--model` option for providers that expose model selection. Defaults SHALL be documented and stable. The `voxtral` provider SHALL expose exactly one supported model, `voxtral-mini-2602`, and SHALL use it by default. The `vertex-gemini` provider SHALL expose `gemini-2.5-flash` and `gemini-2.5-pro`, and SHALL use `gemini-2.5-flash` by default.

#### Scenario: Switch provider
- GIVEN providers `voxtral`, `grok`, and `vertex-gemini` are registered
- WHEN the user runs the pipeline with `--provider grok`
- THEN the Grok-backed provider is used for the transcription stage
- AND switching to `--provider voxtral` re-runs the same audio through the Voxtral-backed provider
- AND switching to `--provider vertex-gemini` re-runs the same audio through the Vertex Gemini-backed provider

#### Scenario: Voxtral default model
- GIVEN provider `voxtral` is selected
- WHEN the user omits `--model`
- THEN the pipeline uses `voxtral-mini-2602`

#### Scenario: Explicit Voxtral model
- GIVEN provider `voxtral` is selected
- WHEN the user runs the pipeline with `--provider voxtral --model voxtral-mini-2602`
- THEN the pipeline uses `voxtral-mini-2602`

#### Scenario: Vertex Gemini default model
- GIVEN provider `vertex-gemini` is selected
- WHEN the user omits `--model`
- THEN the pipeline uses `gemini-2.5-flash`

#### Scenario: Explicit Vertex Gemini model
- GIVEN provider `vertex-gemini` is selected
- WHEN the user runs the pipeline with `--provider vertex-gemini --model gemini-2.5-flash`
- THEN the pipeline uses `gemini-2.5-flash`

#### Scenario: Explicit Vertex Gemini Pro model
- GIVEN provider `vertex-gemini` is selected
- WHEN the user runs the pipeline with `--provider vertex-gemini --model gemini-2.5-pro`
- THEN the pipeline uses `gemini-2.5-pro`

#### Scenario: Unknown provider or model
- GIVEN a provider or model name that is not registered
- WHEN the user invokes the pipeline
- THEN it exits with a non-zero status before any stage runs
- AND the error message lists available providers (or models for the given provider)

### Requirement: Stage isolation and swappability
Each stage SHALL be invoked through a stable interface that does not depend on the implementation details of other stages. Replacing one stage's implementation SHALL NOT require changes to the others. Subtitle improvement SHALL consume raw SRT through the same SRT parser and SHALL NOT depend on provider-specific implementation details beyond the artifact path.

#### Scenario: Replace the extractor
- GIVEN the audio-extraction implementation is replaced
- WHEN the orchestrator runs
- THEN the transcription and optional subtitle-improvement stages work without modification, provided the new extractor still produces an MP3 at the agreed path

#### Scenario: Add a new transcription provider
- GIVEN a third provider is added by registering it under a new name
- WHEN the user selects it via `--provider`
- THEN it is invoked through the same provider interface
- AND optional subtitle improvement processes its raw SRT output unchanged

#### Scenario: Add Vertex Gemini without orchestrator-specific provider logic
- GIVEN provider `vertex-gemini` is registered by the transcription capability
- WHEN the user selects it via `--provider vertex-gemini`
- THEN the orchestrator invokes it through the shared provider interface
- AND the orchestrator does not contain Vertex-specific API, authentication, prompt, or response parsing logic

### Requirement: Single-command UX
The orchestrator SHALL be invocable with a single command requiring only the video path and credentials or provider-specific configuration in environment variables. No interactive prompts or manual file shuffling SHALL be required. Subtitle improvement SHALL be enabled with an explicit CLI option or equivalent non-interactive configuration.

#### Scenario: One-shot raw run
- GIVEN a video and the required API key set in the environment
- WHEN the user runs the orchestrator with the video as the only positional argument
- THEN a raw provider SRT file is produced next to the video without further interaction

#### Scenario: One-shot improved run
- GIVEN a video and the subtitle-improvement option
- WHEN the user runs the orchestrator with the required provider configuration in the environment
- THEN a raw provider SRT file and an improved SRT file are produced next to the video without further interaction

#### Scenario: Missing credentials
- GIVEN the selected provider's required configuration is not set
- WHEN the user runs the orchestrator
- THEN it exits with a non-zero status before any stage runs
- AND the error names the missing configuration value

#### Scenario: One-shot Vertex Gemini run
- GIVEN a video, valid Google Application Default Credentials, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`
- WHEN the user runs the orchestrator with `--provider vertex-gemini`
- THEN a raw Vertex Gemini SRT file is produced next to the video without further interaction
