## ADDED Requirements

### Requirement: Configurable audio splitting
The capability SHALL split an audio file into ordered chunk files using FFmpeg according to caller-supplied configuration. The configuration SHALL include target chunk duration, overlap duration, silence threshold in dB, minimum silence duration, and silence search window.

#### Scenario: Long audio split into configured chunks
- **GIVEN** an audio file whose duration exceeds the configured target chunk duration
- **WHEN** audio splitting is invoked with a target chunk duration and output directory
- **THEN** the capability writes multiple chunk files to the output directory
- **AND** it returns chunk metadata ordered by original audio position
- **AND** each chunk metadata entry includes the chunk path, index, original start time, original end time, start overlap, and end overlap

#### Scenario: Short audio does not split
- **GIVEN** an audio file whose duration does not require a split under the configured target chunk duration
- **WHEN** audio splitting is invoked
- **THEN** the capability returns a single chunk entry referencing the original audio file
- **AND** no unnecessary copied chunk file is created

### Requirement: Silence-aware split point selection
The capability SHALL prefer splitting at detected silence near each target boundary. If no suitable silence exists within the configured search window, the capability SHALL split at the target boundary.

#### Scenario: Silence exists near target boundary
- **GIVEN** a long audio file with a detected silence inside the configured search window around a target split point
- **WHEN** split points are calculated
- **THEN** the selected split point is inside that detected silence
- **AND** the split point is closer to a natural pause than a blind fixed-duration boundary

#### Scenario: No silence near target boundary
- **GIVEN** a long audio file with no detected silence inside the configured search window around a target split point
- **WHEN** split points are calculated
- **THEN** the selected split point is the target split point
- **AND** splitting still completes successfully

### Requirement: FFmpeg command failures are explicit
The capability SHALL fail with a clear error when FFmpeg or ffprobe cannot inspect, analyze, or split the supplied audio.

#### Scenario: Duration probe fails
- **GIVEN** an unreadable or unsupported audio file
- **WHEN** the capability probes audio duration
- **THEN** it exits with a non-zero error
- **AND** the error message identifies the duration probe failure
- **AND** no chunk metadata is returned as successful output

#### Scenario: Chunk extraction fails
- **GIVEN** a readable audio file and an output directory that cannot receive a chunk file
- **WHEN** the capability extracts a chunk with FFmpeg
- **THEN** it exits with a non-zero error
- **AND** the error message identifies the failed chunk extraction

### Requirement: Overlap metadata
The capability SHALL add overlap around internal chunk boundaries and SHALL expose overlap amounts in chunk metadata so downstream consumers can deduplicate repeated transcription content.

#### Scenario: Internal chunks include overlap
- **GIVEN** an audio file split into at least three chunks with a configured overlap duration
- **WHEN** chunks are created
- **THEN** chunks after the first include start overlap metadata greater than zero
- **AND** chunks before the last include end overlap metadata greater than zero
- **AND** no chunk start time is before zero
- **AND** no chunk end time is after the source audio duration

#### Scenario: Boundary chunks clamp overlap
- **GIVEN** an audio file split into chunks with a configured overlap duration
- **WHEN** the first and last chunks are created
- **THEN** the first chunk starts at the beginning of the source audio
- **AND** the last chunk ends at the end of the source audio

### Requirement: Chunked SRT merge
The capability SHALL merge SRT outputs produced from audio chunks into a single SRT whose cue timestamps align to the original audio timeline.

#### Scenario: Chunk timestamps are offset
- **GIVEN** two chunk SRT files with cue timestamps relative to each chunk start
- **WHEN** the chunk SRT files are merged using chunk metadata
- **THEN** cues from later chunks have their timestamps offset by the chunk original start time
- **AND** the merged SRT cues are ordered by time
- **AND** cue indexes are rewritten sequentially from one

#### Scenario: Duplicate overlap cues are removed
- **GIVEN** adjacent chunk SRT files contain equivalent cue text in their overlap region
- **WHEN** the chunk SRT files are merged
- **THEN** the duplicate overlap cue appears only once in the merged SRT
- **AND** non-overlapping cues from both chunks are preserved

#### Scenario: No text match uses time cutoff
- **GIVEN** adjacent chunk SRT files contain overlap regions without sufficiently similar cue text
- **WHEN** the chunk SRT files are merged
- **THEN** the merge uses overlap timing to avoid keeping repeated boundary content where possible
- **AND** the merged SRT remains valid and time-ordered
