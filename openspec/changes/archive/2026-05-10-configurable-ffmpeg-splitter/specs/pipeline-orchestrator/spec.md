## ADDED Requirements

### Requirement: Provider-owned splitting boundary
The orchestrator SHALL NOT expose or implement audio splitting. The orchestrator SHALL continue to extract one audio file and invoke the selected provider once; any chunking required by the selected provider SHALL happen behind the provider boundary.

#### Scenario: Pipeline invokes provider once
- **GIVEN** the orchestrator is invoked for a provider that may use internal chunking
- **WHEN** the pipeline runs successfully
- **THEN** it extracts one MP3 audio file
- **AND** it invokes the selected transcription provider once with that audio file
- **AND** it writes the raw provider SRT at `<video>.<provider>.raw.srt`

#### Scenario: Splitter options are not accepted by orchestrator
- **GIVEN** a caller attempts to pass a splitter-specific option to the pipeline CLI
- **WHEN** arguments are parsed
- **THEN** the pipeline rejects the unknown option
- **AND** no extraction or provider transcription starts

### Requirement: Split artifact lifecycle
The orchestrator SHALL remain responsible for the extracted audio artifact lifecycle only. Providers that split internally SHALL manage their temporary chunk audio and chunk SRT artifacts.

#### Scenario: Successful split run cleans temporary chunks
- **GIVEN** a provider uses internal chunking and the raw SRT is written successfully
- **WHEN** the orchestrator completes the raw transcription stage
- **THEN** the orchestrator removes the extracted MP3 audio file
- **AND** the merged raw SRT remains on disk

#### Scenario: Failed split run does not declare cleanup success
- **GIVEN** a provider uses internal chunking and one chunk transcription fails
- **WHEN** the orchestrator stops the pipeline
- **THEN** it returns a non-zero status with a clear error
- **AND** it does not write a partial merged raw SRT
- **AND** it keeps the extracted MP3 audio file for diagnosis
