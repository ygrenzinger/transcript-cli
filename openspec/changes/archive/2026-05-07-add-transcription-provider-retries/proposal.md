## Why

Transient provider failures during transcription currently fail the entire run even when the same request would likely succeed moments later. Long transcription jobs are expensive to restart manually, so provider calls should automatically absorb short-lived network, rate-limit, and service-side interruptions.

## What Changes

- Add always-on retry behavior for transient transcription provider call failures.
- Retry applies to both the full `video-to-srt` pipeline and the standalone `transcribe-srt` command.
- Retry up to 3 times after the initial attempt, using exponential backoff delays of 1s, 2s, and 4s.
- Respect Grok HTTP 429 `Retry-After` responses when present instead of the default delay.
- Preserve permanent failure behavior: non-transient provider errors still fail clearly and do not write partial SRT output.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `audio-to-srt-transcription`: extend provider failure handling to retry transient provider call failures before returning a final error.

## Impact

- Affects transcription provider invocation behavior in `python/providers.py` and callers that use registered providers.
- Affects `video-to-srt` and `transcribe-srt` runtime behavior by making transient transcription failures take longer before final failure.
- Adds tests for retryable versus non-retryable provider failures, retry exhaustion, and `Retry-After` handling.
- No new CLI flags or external dependencies are expected.
