## ADDED Requirements

### Requirement: Provider-owned chunked transcription
The transcription capability SHALL allow a provider to use prepared audio chunks internally while preserving the caller-facing contract of invoking the provider once with one audio path and receiving one SRT file at the requested output path.

#### Scenario: Provider transcribes prepared chunks
- **GIVEN** a registered transcription provider with a split policy
- **WHEN** the provider is invoked through the existing provider interface
- **THEN** the provider prepares audio chunks internally
- **AND** its single-chunk transcription operation receives a single chunk audio path and a chunk-specific SRT output path
- **AND** the final caller-requested SRT is written only after all chunks transcribe successfully

#### Scenario: Chunked transcription preserves provider options
- **GIVEN** a provider with a split policy is invoked with a model and language hint
- **WHEN** the provider transcribes each chunk internally
- **THEN** the selected model and language hint are passed to every provider call

#### Scenario: Chunk failure prevents final output
- **GIVEN** a provider fails while transcribing one of several chunks
- **WHEN** the provider handles the chunk failure
- **THEN** the transcription command exits with a non-zero provider error
- **AND** it does not write a partial final SRT file

#### Scenario: Provider split policies
- **GIVEN** the default provider registry is used
- **WHEN** provider split policies are inspected
- **THEN** provider `grok` does not use audio chunking
- **AND** provider `voxtral` does not use audio chunking
- **AND** provider `vertex-gemini` uses 900-second chunks
- **AND** provider `sherpa-parakeet` uses 120-second chunks with 15-second overlap

### Requirement: Chunked transcription retry behavior
Provider-owned chunked transcription SHALL apply the existing transient provider retry policy independently to each chunk provider call.

#### Scenario: Transient chunk failure is retried
- **GIVEN** a provider call for one chunk fails with a transient provider call failure
- **WHEN** chunked transcription handles that chunk
- **THEN** the existing retry policy is applied before the chunk is treated as failed
- **AND** successful retry allows chunked transcription to continue to later chunks

#### Scenario: Retry exhaustion stops chunked transcription
- **GIVEN** a provider call for one chunk exhausts the existing retry policy
- **WHEN** chunked transcription handles that failure
- **THEN** no later chunks are transcribed
- **AND** no final merged SRT is written
