## ADDED Requirements

### Requirement: Transient provider retry
The transcription capability SHALL automatically retry transient provider call failures before returning a final provider error. Retry behavior SHALL be always enabled, SHALL apply to all registered transcription providers invoked through the shared provider interface, and SHALL be used by both the full video pipeline and the standalone transcription command. The capability SHALL retry up to 3 times after the initial attempt, using default backoff delays of 1s, 2s, and 4s. For Grok HTTP 429 responses that include `Retry-After`, the capability SHALL use the provider-supplied retry delay for that retry attempt instead of the default backoff delay.

#### Scenario: Transient failure succeeds after retry
- **GIVEN** a registered transcription provider fails a transcription attempt with a transient provider call failure
- **WHEN** a later retry attempt succeeds
- **THEN** the transcription command writes the requested SRT output
- **AND** the command exits with a zero status

#### Scenario: Retry exhaustion returns clear error
- **GIVEN** a registered transcription provider continues to fail with transient provider call failures
- **WHEN** the initial attempt and 3 retry attempts have all failed
- **THEN** the transcription command exits with a non-zero status
- **AND** the final error message clearly identifies the provider transcription failure
- **AND** no partial SRT file is written

#### Scenario: Non-transient failure is not retried
- **GIVEN** a registered transcription provider fails because of a non-transient condition such as missing credentials, unsupported model, malformed successful response, or empty transcription result
- **WHEN** the provider failure is handled
- **THEN** the transcription command exits with a non-zero status without exhausting retry attempts
- **AND** the error message describes the non-transient failure

#### Scenario: Grok rate limit respects Retry-After
- **GIVEN** the Grok provider receives an HTTP 429 response with a `Retry-After` value
- **WHEN** the retry delay is selected for that failed attempt
- **THEN** the retry waits according to the `Retry-After` value instead of the default exponential backoff delay

#### Scenario: Retry applies to full pipeline and standalone command
- **GIVEN** a transient provider call failure occurs during transcription
- **WHEN** transcription is invoked through either `video-to-srt` or `transcribe-srt`
- **THEN** the same retry policy is applied before the command reports final success or failure
