## Why

The transcription pipeline already supports pluggable providers, but it cannot use Google Vertex AI Gemini as a transcription backend. Adding a Vertex Gemini provider gives users another high-quality transcription option while keeping provider-specific authentication, model selection, and output parsing behind the existing provider boundary.

## What Changes

- Add a registered transcription provider named `vertex-gemini`.
- Use `gemini-2.5-flash` as the default Vertex Gemini model.
- Configure the provider through Google Application Default Credentials plus `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
- Evolve provider readiness checks from a single required environment variable to multiple provider-scoped configuration requirements.
- Allow providers such as Vertex Gemini to emit model-derived subtitle segment timestamps when the underlying API does not expose native word or segment timing metadata.
- Document Vertex Gemini timestamp output as approximate raw provider output.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `audio-to-srt-transcription`: Add the `vertex-gemini` provider, support multiple required provider config values, and clarify timestamp requirements for providers without native timing metadata.
- `pipeline-orchestrator`: Include `vertex-gemini` in provider/model selection behavior and require pre-stage validation of its provider-specific configuration.

## Impact

- Affected code: `python/providers.py`, provider registration, provider readiness validation, dependency metadata, and user documentation.
- Affected CLI behavior: `--provider vertex-gemini` selects the Vertex AI Gemini-backed provider and defaults to `gemini-2.5-flash` unless `--model` is supplied.
- New runtime dependency: Google Gen AI Python SDK (`google-genai`).
- External systems: Google Vertex AI Gemini API and local/cloud Google Application Default Credentials.
