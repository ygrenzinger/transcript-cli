## Context

The transcription capability currently exposes a small provider interface: callers resolve a provider and invoke `provider.transcribe(...)`. Both `video-to-srt` and `transcribe-srt` use this same interface, while provider implementations perform a single underlying SDK or HTTP request and convert the result into an SRT file. Any provider call failure is currently wrapped as `ProviderError` and returned to the caller immediately.

Provider-side transcription calls can fail transiently because of network interruption, timeout, rate limiting, or temporary service errors. Since transcription runs can be long and manual restarts are costly, retry behavior should live at the shared transcription provider boundary rather than only in the pipeline command.

## Goals / Non-Goals

**Goals:**

- Retry transient transcription provider call failures automatically for all callers of registered providers.
- Apply the same always-on retry policy to `video-to-srt` and `transcribe-srt` without adding CLI flags.
- Use 3 retries after the initial attempt, with default delays of 1s, 2s, and 4s.
- Respect Grok HTTP 429 `Retry-After` values when available.
- Preserve clear final errors and avoid partial SRT files after retry exhaustion.

**Non-Goals:**

- Add user-configurable retry counts, delays, or feature flags.
- Retry validation, standardization, audio extraction, or permanent provider failures.
- Add new dependencies for retry/backoff behavior.
- Add provider-level progress percentages or ETA reporting.

## Decisions

- Centralize retry behavior near provider invocation rather than inside `pipeline.py` only. This keeps standalone `transcribe-srt` and the full pipeline consistent, and avoids duplicating retry loops in each caller.
- Keep provider implementations responsible for one transcription attempt. A shared retry helper or wrapper can call that operation repeatedly, while providers continue to own request construction and response-to-SRT conversion.
- Classify retryable failures conservatively. Network timeouts, connection errors, HTTP 429, and HTTP 5xx responses should be retryable; missing credentials, unsupported models, malformed successful responses, empty transcription results, and validation failures should fail without retry.
- Preserve atomic output behavior. Providers already write SRT through an atomic write path after successful response conversion; retry should not expose partial output files from failed attempts.
- Use default exponential delays of 1s, 2s, and 4s for the 3 retries after the initial attempt. For Grok HTTP 429 responses with `Retry-After`, use the provider-supplied delay for that retry attempt instead of the default exponential delay.
- Keep retry observability simple. The pipeline can optionally emit structured retry progress in the transcription stage, but the core requirement is successful automatic retry and clear final failure; standalone transcription should at minimum report the final error.

## Risks / Trade-offs

- Retrying non-idempotent provider operations could duplicate provider-side work or cost. Mitigation: retry only before an SRT is written locally and only for failures that indicate the request did not complete successfully from the caller's perspective.
- Conservative transient classification may miss some provider SDK-specific temporary failures. Mitigation: start with known HTTP/network cases and keep the classification isolated so provider-specific cases can be added later.
- Always-on retries make permanent transient-looking failures take longer to surface. Mitigation: cap retries at 3 and keep total default delay bounded to 7 seconds before final failure, unless a provider explicitly returns `Retry-After` for rate limiting.
- `Retry-After` can be unexpectedly long. Mitigation: implementation should parse standard seconds or HTTP-date values and may cap unreasonable values if needed to preserve command usability.
