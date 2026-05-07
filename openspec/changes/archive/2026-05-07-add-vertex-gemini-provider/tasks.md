## 1. Provider Configuration Interface

- [x] 1.1 Replace the provider protocol's single `env_var` field with a multiple-value configuration contract such as `required_env_vars`.
- [x] 1.2 Update Voxtral and Grok providers to declare their existing API key requirements through the new contract.
- [x] 1.3 Update provider readiness validation to fail fast for every missing required configuration value and keep unsupported model validation before transcription starts.
- [x] 1.4 Add or update tests covering missing single-value and multi-value provider configuration errors.

## 2. Vertex Gemini Provider

- [x] 2.1 Add the `google-genai` runtime dependency and package/module metadata needed by the Python project.
- [x] 2.2 Implement `VertexGeminiProvider` registered as `vertex-gemini` with default model `gemini-2.5-flash`.
- [x] 2.3 Initialize the Google Gen AI client in Vertex AI mode using `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and Application Default Credentials.
- [x] 2.4 Send MP3 bytes and a strict transcription prompt to Gemini with structured JSON response configuration.
- [x] 2.5 Parse Gemini JSON segments into ordered SRT cues and reject malformed, empty, non-numeric, or non-positive-duration output without writing partial SRT.
- [x] 2.6 Wrap Google SDK failures in clear `ProviderError` messages compatible with existing retry handling.

## 3. CLI, Docs, and Discoverability

- [x] 3.1 Ensure `list_providers()` includes `vertex-gemini`, its default model, and supported model list.
- [x] 3.2 Update README environment setup with Vertex Gemini configuration and ADC guidance.
- [x] 3.3 Document that Vertex Gemini timestamps are model-derived and approximate.
- [x] 3.4 Confirm `video-to-srt --provider vertex-gemini` writes `<video>.vertex-gemini.raw.srt` and optional improved output remains unchanged.

## 4. Verification

- [x] 4.1 Add unit tests for Vertex Gemini response parsing and provider registration without making live Google API calls.
- [x] 4.2 Add tests that pipeline provider/model selection works for `vertex-gemini` without adding Vertex-specific orchestrator logic.
- [x] 4.3 Run the Python test suite.
- [x] 4.4 Run OpenSpec validation for `add-vertex-gemini-provider` and resolve any proposal/spec/task issues.
