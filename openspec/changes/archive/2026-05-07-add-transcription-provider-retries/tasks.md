## 1. Retry Model

- [x] 1.1 Add a shared retry policy for transcription provider calls with 3 retries after the initial attempt and default delays of 1s, 2s, and 4s.
- [x] 1.2 Add retryable failure classification for transient network, timeout, HTTP 429, and HTTP 5xx provider call failures.
- [x] 1.3 Add `Retry-After` parsing for Grok HTTP 429 responses and use it instead of the default delay when present.
- [x] 1.4 Ensure non-transient provider errors such as missing credentials, unsupported model, malformed response, and empty transcription result are not retried.

## 2. Command Integration

- [x] 2.1 Route `transcribe-srt` provider invocation through the shared retry behavior without adding CLI flags.
- [x] 2.2 Route `video-to-srt` transcription stage through the same shared retry behavior without changing provider selection arguments.
- [x] 2.3 Preserve atomic SRT output behavior so exhausted retries do not leave partial output files.

## 3. Verification

- [x] 3.1 Add tests proving a transient provider failure succeeds when a later retry succeeds.
- [x] 3.2 Add tests proving transient retry exhaustion attempts the initial call plus 3 retries and returns a clear final error.
- [x] 3.3 Add tests proving non-transient provider failures are not retried.
- [x] 3.4 Add tests proving Grok HTTP 429 `Retry-After` controls the retry delay.
- [x] 3.5 Add tests or smoke coverage showing both `video-to-srt` and `transcribe-srt` use the retry policy.
- [x] 3.6 Run the relevant Python test suite and fix regressions.
