# audio-to-srt-transcription Specification

## Purpose
Transform an audio file into an SRT subtitle file. This capability defines a **provider interface** so that multiple transcription backends (e.g. Mistral Voxtral, xAI Grok) can be plugged in interchangeably. Providers are responsible for the speech-to-text step and for emitting cues in SRT form. The canonical shared output structure across all providers is the SRT file itself (not a provider-specific structured payload). Concerns related to enforcing readability best-practices live in the `srt-standardization` capability; correctness checks live in `srt-validation`.

## Requirements

### Requirement: Provider contract
A transcription provider SHALL implement a single operation: given an audio file path and an optional language hint, produce an SRT file at a caller-specified path.

#### Scenario: Successful transcription
- GIVEN an MP3 audio file with intelligible speech
- WHEN a registered provider is invoked with that file path
- THEN it writes an SRT file to the caller-specified output path
- AND it exits with a zero status

#### Scenario: Provider failure
- GIVEN the underlying STT API returns an error (e.g. invalid credentials, network failure, unsupported audio)
- WHEN the provider is invoked
- THEN it exits with a non-zero status and a clear error message
- AND it does not write a partial SRT file

### Requirement: Transient provider retry
The transcription capability SHALL automatically retry transient provider call failures before returning a final provider error. Retry behavior SHALL be always enabled, SHALL apply to all registered transcription providers invoked through the shared provider interface, and SHALL be used by both the full video pipeline and the standalone transcription command. The capability SHALL retry up to 3 times after the initial attempt, using default backoff delays of 1s, 2s, and 4s. For Grok HTTP 429 responses that include `Retry-After`, the capability SHALL use the provider-supplied retry delay for that retry attempt instead of the default backoff delay.

#### Scenario: Transient failure succeeds after retry
- GIVEN a registered transcription provider fails a transcription attempt with a transient provider call failure
- WHEN a later retry attempt succeeds
- THEN the transcription command writes the requested SRT output
- AND the command exits with a zero status

#### Scenario: Retry exhaustion returns clear error
- GIVEN a registered transcription provider continues to fail with transient provider call failures
- WHEN the initial attempt and 3 retry attempts have all failed
- THEN the transcription command exits with a non-zero status
- AND the final error message clearly identifies the provider transcription failure
- AND no partial SRT file is written

#### Scenario: Non-transient failure is not retried
- GIVEN a registered transcription provider fails because of a non-transient condition such as missing credentials, unsupported model, malformed successful response, or empty transcription result
- WHEN the provider failure is handled
- THEN the transcription command exits with a non-zero status without exhausting retry attempts
- AND the error message describes the non-transient failure

#### Scenario: Grok rate limit respects Retry-After
- GIVEN the Grok provider receives an HTTP 429 response with a `Retry-After` value
- WHEN the retry delay is selected for that failed attempt
- THEN the retry waits according to the `Retry-After` value instead of the default exponential backoff delay

#### Scenario: Retry applies to full pipeline and standalone command
- GIVEN a transient provider call failure occurs during transcription
- WHEN transcription is invoked through either `video-to-srt` or `transcribe-srt`
- THEN the same retry policy is applied before the command reports final success or failure

### Requirement: Pluggable provider selection
The capability SHALL allow the caller to select a provider by name at invocation time. New providers SHALL be addable without modifying existing providers or the orchestrator's core logic.

#### Scenario: Provider switch
- GIVEN providers `voxtral` and `grok` are registered
- WHEN the caller specifies `--provider grok` (or equivalent)
- THEN the Grok-backed implementation is used to produce the SRT
- AND switching to `--provider voxtral` for the same audio uses the Voxtral-backed implementation instead

#### Scenario: Unknown provider
- GIVEN a provider name that is not registered
- WHEN the caller selects it
- THEN the capability exits with a non-zero status and lists the available providers in its error message

### Requirement: Provider-scoped model selection
The capability SHALL accept a global `--model` argument (or equivalent) at invocation time. The model value is interpreted within the selected provider's model namespace. The `voxtral` provider SHALL expose exactly one supported model: `voxtral-mini-2602`.

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

#### Scenario: Unsupported model for selected provider
- GIVEN provider `voxtral` is selected and model `grok-transcribe-1` is not supported by `voxtral`
- WHEN the caller invokes the capability with `--provider voxtral --model grok-transcribe-1`
- THEN the capability exits with a non-zero status (fail fast)
- AND it returns a clear error that the model is unsupported for that provider
- AND it does not start a transcription attempt

### Requirement: Provider and model discoverability
The capability SHALL expose a discoverability command (or equivalent API) that lists registered providers and the models supported by each provider.

#### Scenario: List providers and models
- GIVEN at least two registered providers with distinct model sets
- WHEN the caller invokes the discoverability command
- THEN the output includes each provider name
- AND the output lists the supported models for each provider in a machine-readable or clearly parseable form

### Requirement: Word-level timing fidelity
Each provider SHALL produce SRT cues whose timestamps reflect the underlying speech timing returned by the STT model, with millisecond precision.

#### Scenario: Cue timing reflects speech
- GIVEN a transcription where the words "hello world" are spoken from 1.250 s to 2.480 s
- WHEN the provider emits the corresponding cue
- THEN the cue's start and end timestamps match those bounds within ±50 ms

### Requirement: Language hint
The capability SHALL accept an optional language code (e.g. `en`, `fr`) and forward it to the provider when supplied. Providers MAY use it to improve accuracy.

#### Scenario: Language hint provided
- GIVEN the caller passes `--language fr`
- WHEN the provider is invoked
- THEN it forwards the hint to its underlying STT API in the form that API expects

#### Scenario: No language hint
- GIVEN no language is specified
- WHEN the provider is invoked
- THEN it relies on the underlying API's auto-detection (or default), without erroring

### Requirement: Provider boundary
A provider SHALL NOT be responsible for enforcing readability best-practices (cps, line length, inter-cue gap). Its output is treated as raw transcription cues that the orchestrator will pass through `srt-validation` and `srt-standardization`.

#### Scenario: Raw provider output may exceed best-practice limits
- GIVEN a provider emits a cue whose text exceeds 84 characters or whose duration exceeds 7 s
- WHEN the orchestrator receives this cue
- THEN it is the orchestrator's responsibility (via the standardization step) to reshape such cues — the provider is not faulted for them
