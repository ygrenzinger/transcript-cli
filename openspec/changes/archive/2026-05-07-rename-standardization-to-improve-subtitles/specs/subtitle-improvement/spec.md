## ADDED Requirements

### Requirement: Optional subtitle improvement
The system SHALL provide an optional subtitle improvement step that reads a raw provider SRT and writes a readability-improved SRT without modifying the raw input file.

#### Scenario: Improvement writes separate artifact
- **GIVEN** a raw provider SRT at `path/to/clip.voxtral.raw.srt`
- **WHEN** subtitle improvement runs for that file
- **THEN** it writes `path/to/clip.voxtral.improved.srt`
- **AND** `path/to/clip.voxtral.raw.srt` remains unchanged

### Requirement: Invalid raw cue filtering
Subtitle improvement SHALL discard input cues whose end timestamp is less than or equal to their start timestamp before applying readability, speaker, gap, or re-indexing rules.

#### Scenario: Zero-duration provider segment is removed
- **GIVEN** an input cue with identical start and end timestamps
- **WHEN** subtitle improvement runs
- **THEN** that cue is omitted from the improved output
- **AND** the remaining cues are re-indexed sequentially

#### Scenario: Negative-duration provider segment is removed
- **GIVEN** an input cue whose end timestamp is earlier than its start timestamp
- **WHEN** subtitle improvement runs
- **THEN** that cue is omitted from the improved output
- **AND** subtitle improvement continues for the remaining cues

### Requirement: Cue duration limits
Every cue in the improved output SHALL last no longer than 7.0 seconds. The target duration is 1-6 seconds. Cues shorter than 1.0 second are permitted only when forced by a speaker change or a brief utterance with no following speech.

#### Scenario: Long cue is split
- **GIVEN** an input cue whose duration exceeds 7.0 seconds
- **WHEN** subtitle improvement runs
- **THEN** the cue is split into multiple cues, each no longer than 7.0 seconds

#### Scenario: Short utterance preserved
- **GIVEN** an input cue containing a single short word followed by a long pause
- **WHEN** subtitle improvement runs
- **THEN** the cue is emitted even if shorter than 1.0 second

### Requirement: Reading speed
Every cue's displayed text SHALL stay at or below 17 characters per second of displayed duration. The target is 12-15 characters per second.

#### Scenario: Cue exceeds reading-speed budget
- **GIVEN** an input cue whose text length divided by its duration exceeds 17 characters per second
- **WHEN** subtitle improvement runs
- **THEN** the cue is either split into multiple cues or its end time is extended into following silence without overlapping the next cue until it is at or below 17 characters per second

### Requirement: Line and character limits
Every cue in the improved output SHALL contain at most 2 lines, each line at most 42 characters. Total cue text SHALL NOT exceed 84 displayed characters.

#### Scenario: Long single-line cue is wrapped
- **GIVEN** a cue body whose text would render as more than 42 characters on one line
- **WHEN** subtitle improvement runs
- **THEN** the text is wrapped onto 2 lines of at most 42 characters, breaking on whitespace
- **AND** the line break favors a clause boundary over arbitrary mid-clause wrapping

#### Scenario: Cue text exceeds 84 characters
- **GIVEN** a cue whose text exceeds 84 characters
- **WHEN** subtitle improvement runs
- **THEN** it is split into two or more cues at the nearest sentence or word boundary

### Requirement: Boundary preferences
When subtitle improvement needs to split a cue, it SHALL choose the split point in this priority order: sentence-ending punctuation, clause punctuation, then the nearest word boundary that satisfies all other limits.

#### Scenario: Sentence terminator available
- **GIVEN** a candidate split window that contains a sentence-ending punctuation mark
- **WHEN** subtitle improvement splits the cue
- **THEN** the new boundary lands at that terminator

#### Scenario: No punctuation in window
- **GIVEN** no sentence or clause boundary is present in the candidate split window
- **WHEN** subtitle improvement splits the cue
- **THEN** the new boundary lands at the last word that satisfies duration, reading-speed, and character limits

### Requirement: Speaker change forces cue boundary
An improved cue SHALL contain text from only one speaker. If the input contains a speaker change inside a single cue, subtitle improvement SHALL split the cue at that change.

#### Scenario: Mid-cue speaker change
- **GIVEN** an input cue containing words from speakers A and then B
- **WHEN** subtitle improvement runs
- **THEN** A's words form one cue and B's words form a new cue starting at B's first word

### Requirement: Inter-cue gap
Consecutive cues in the improved output SHALL be separated by at least 80 ms of silence. If the raw input has cues that touch or overlap, subtitle improvement SHALL adjust their boundaries to enforce the gap while never reducing a cue below 0.5 s of duration.

#### Scenario: Touching cues
- **GIVEN** cue N ends at `00:00:12,000` and cue N+1 starts at `00:00:12,020`
- **WHEN** subtitle improvement runs
- **THEN** either cue N's end is shortened or cue N+1's start is delayed so the gap is at least 80 ms
- **AND** no resulting cue has duration less than 0.5 s

### Requirement: Speaker labeling
When the input indicates more than one distinct speaker, every improved output cue SHALL begin with a `Speaker N: ` prefix on its first line. When only one speaker is detected, no prefix SHALL be added.

#### Scenario: Multi-speaker file
- **GIVEN** provider output with at least 2 distinct speakers
- **WHEN** subtitle improvement runs
- **THEN** every cue's first line begins with `Speaker N: `

#### Scenario: Single-speaker file
- **GIVEN** provider output with exactly one speaker
- **WHEN** subtitle improvement runs
- **THEN** no speaker prefix is added to any cue

### Requirement: Idempotence
Running subtitle improvement on its own output SHALL produce a byte-identical file.

#### Scenario: Second pass is a no-op
- **GIVEN** a file produced by a first run of subtitle improvement
- **WHEN** subtitle improvement runs again on that file
- **THEN** the resulting file is byte-identical to the input

### Requirement: Re-indexing
After any reshaping, the improved output SHALL have cues indexed sequentially from `1`, with no gaps or duplicates.

#### Scenario: Indices after splitting
- **GIVEN** subtitle improvement splits cue 5 into two cues
- **WHEN** the output is written
- **THEN** the resulting file is renumbered so all indices are sequential and 1-based
