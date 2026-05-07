## Context

The current transcription provider interface supports `voxtral` and `grok` through a shared `TranscriptionProvider` protocol. Each provider resolves a provider-scoped model, checks one required environment variable, performs the API call, converts the provider response into shared `Cue` objects, and writes the caller-specified SRT path atomically.

Vertex AI Gemini is different from the existing providers because it uses Google Application Default Credentials plus project/location configuration, and it behaves as a multimodal generative model rather than a dedicated speech-to-text API that returns native word or segment timings. The provider still fits the pipeline if it owns its prompt, JSON response schema, timestamp caveats, and SRT conversion behind the same provider boundary.

## Goals / Non-Goals

**Goals:**

- Register a provider named `vertex-gemini` with default model `gemini-2.5-flash`.
- Use Vertex AI mode from the Google Gen AI Python SDK with Application Default Credentials.
- Validate `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` before any pipeline stage runs.
- Preserve the existing `--provider`, `--model`, and `--language` CLI shape.
- Convert structured Gemini output into raw SRT cues without changing downstream subtitle improvement behavior.
- Document that Vertex Gemini timestamps are model-derived and approximate.

**Non-Goals:**

- Do not add a separate Gemini Developer API key mode.
- Do not add new CLI flags for Google project, location, credentials, prompt tuning, or safety settings.
- Do not require Vertex Gemini to satisfy dedicated STT word-level timing fidelity in the first version.
- Do not change raw/improved output filename conventions.

## Decisions

### Provider Naming

Use `vertex-gemini` as the provider name. This is explicit that the provider uses Vertex AI rather than the Gemini Developer API, and it keeps output artifacts unambiguous: `<video>.vertex-gemini.raw.srt` and `<video>.vertex-gemini.improved.srt`.

Alternatives considered: `gemini` is shorter but ambiguous across Google API surfaces; `gemini-vertex` is less aligned with the product name order.

### Provider Configuration

Replace the single `env_var` provider field with a provider-scoped collection such as `required_env_vars`. Existing API-key providers will expose one required variable (`MISTRAL_API_KEY` or `XAI_API_KEY`), while `vertex-gemini` will expose `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.

Application Default Credentials are required but are not represented as an environment variable because they may come from local `gcloud` ADC files, workload identity, or platform credentials. Missing or invalid ADC will be reported as a provider failure when the Google SDK initializes or calls Vertex AI.

Alternatives considered: keeping `env_var` and checking the second variable inside the provider would be smaller but would make readiness behavior inconsistent; adding Google-specific CLI flags would leak provider configuration into the orchestrator.

### Model Selection

The provider will default to `gemini-2.5-flash`. Additional Gemini models may be registered as provider-scoped aliases if they are intended to be supported, but the first version only needs the default unless implementation tests require explicit alternate model coverage.

### Gemini Request and Response Shape

The provider will send the extracted MP3 bytes using `types.Part.from_bytes(..., mime_type="audio/mp3")` and a prompt asking Gemini to transcribe the audio into subtitle-ready segments. The response should be requested as JSON using the SDK's structured-output support.

The expected response shape should be minimal and provider-owned:

```json
{
  "segments": [
    {"start": 0.0, "end": 2.4, "text": "..."}
  ]
}
```

The provider will reject empty text, missing segments, non-numeric timestamps, non-positive durations, or malformed JSON as provider errors. Readability reshaping remains the responsibility of the existing subtitle improvement step.

### Timestamp Contract

The core transcription spec will distinguish between native timing metadata and model-derived timing. Dedicated STT providers must preserve native timing metadata when available. Providers without native timing metadata may emit approximate model-derived segment timestamps if they still produce ordered valid cues and document the limitation.

This keeps `vertex-gemini` honest without weakening the timing expectations for `voxtral` and `grok`.

## Risks / Trade-offs

- Model-derived timestamps may drift from the spoken audio. Mitigation: document the limitation, keep raw output separate, and let users compare providers.
- Gemini may return malformed or schema-incompatible JSON. Mitigation: use structured JSON configuration when possible and fail with a clear provider error instead of writing partial SRT.
- Google SDK exceptions may not expose HTTP status metadata in the same way as `requests`. Mitigation: keep retry behavior best-effort through the existing provider error wrapper and add targeted retry mapping only if SDK error shapes are confirmed during implementation.
- Audio files may be large for inline byte upload. Mitigation: preserve the current extracted MP3 flow for the first version; consider file upload or chunking only if real usage exposes size limits.
- ADC failures may surface later than environment variable checks. Mitigation: validate project/location before pipeline stages and report Google SDK authentication failures as provider readiness/transcription errors.
