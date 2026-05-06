# srt-standardization Specification

## Purpose
Reshape a raw SRT file (as produced by any transcription provider) so that it conforms to widely accepted subtitle readability and timing best-practices (BBC, Netflix, EBU-TT-D guidelines). Standardization is **idempotent**: running it again on its own output produces the same file. It owns the rules — providers do not.

## Requirements

### Requirement: Cue duration limits
Every cue in the standardized output SHALL last no longer than 7.0 seconds. The target duration is 1–6 seconds. Cues SHORTER than 1.0 second are permitted only when forced by a speaker change or a brief utterance with no following speech.

#### Scenario: Long cue is split
- GIVEN an input cue whose duration exceeds 7.0 seconds
- WHEN standardization runs
- THEN the cue is split into multiple cues, each ≤ 7.0 seconds

#### Scenario: Short utterance preserved
- GIVEN an input cue containing a single short word followed by a long pause
- WHEN standardization runs
- THEN the cue is emitted as-is even if shorter than 1.0 second

### Requirement: Reading speed (characters per second)
Every cue's displayed text SHALL stay at or below 17 characters per second of displayed duration. The target is 12–15 cps.

#### Scenario: Cue exceeds cps budget
- GIVEN an input cue whose text length divided by its duration exceeds 17 cps
- WHEN standardization runs
- THEN the cue is either split into multiple cues or its end time is extended into the following silence (without overlapping the next cue) until cps ≤ 17

### Requirement: Line and character limits
Every cue SHALL contain at most 2 lines, each line at most 42 characters. Total cue text therefore SHALL NOT exceed 84 characters.

#### Scenario: Long single-line cue is wrapped
- GIVEN a cue body whose text would render as more than 42 characters on one line
- WHEN standardization runs
- THEN the text is wrapped onto 2 lines of ≤ 42 characters, breaking on whitespace
- AND the line break favors a clause boundary (after punctuation or before a conjunction) over arbitrary mid-clause wrapping

#### Scenario: Cue text exceeds 84 characters
- GIVEN a cue whose text exceeds 84 characters
- WHEN standardization runs
- THEN it is split into two or more cues at the nearest sentence or word boundary

### Requirement: Boundary preferences
When standardization needs to split a cue, it SHALL choose the split point in this priority order: (1) sentence-ending punctuation (`.`, `?`, `!`), (2) clause punctuation (`,`, `;`, `:`), (3) the nearest word boundary that satisfies all other limits.

#### Scenario: Sentence terminator available
- GIVEN a candidate split window that contains a sentence-ending punctuation mark
- WHEN standardization splits the cue
- THEN the new boundary lands at that terminator

#### Scenario: No punctuation in window
- GIVEN no sentence or clause boundary is present in the candidate window
- WHEN standardization splits the cue
- THEN the new boundary lands at the last word that satisfies duration, cps, and character limits

### Requirement: Speaker change forces cue boundary
A standardized cue SHALL contain text from only one speaker. If the input contains a speaker change inside a single cue, standardization SHALL split the cue at that change.

#### Scenario: Mid-cue speaker change
- GIVEN an input cue containing words from speakers A and then B
- WHEN standardization runs
- THEN A's words form one cue and B's words form a new cue starting at B's first word

### Requirement: Inter-cue gap
Consecutive cues in the standardized output SHALL be separated by at least 80 ms of silence. If the raw input has cues that touch or overlap, standardization SHALL adjust their boundaries to enforce the gap, while never reducing a cue below 0.5 s of duration.

#### Scenario: Touching cues
- GIVEN cue N ends at `00:00:12,000` and cue N+1 starts at `00:00:12,020`
- WHEN standardization runs
- THEN either cue N's end is shortened or cue N+1's start is delayed so the gap is ≥ 80 ms
- AND no resulting cue has duration < 0.5 s

### Requirement: Speaker labeling
When the input indicates more than one distinct speaker (via per-cue prefixes or side-channel metadata from the provider), every output cue SHALL begin with a `Speaker N: ` prefix on its first line. When only one speaker is detected, no prefix SHALL be added.

#### Scenario: Multi-speaker file
- GIVEN provider output with ≥ 2 distinct speakers
- WHEN standardization runs
- THEN every cue's first line begins with `Speaker N: `

#### Scenario: Single-speaker file
- GIVEN provider output with exactly one speaker
- WHEN standardization runs
- THEN no speaker prefix is added to any cue

### Requirement: Idempotence
Running standardization on its own output SHALL produce a byte-identical file.

#### Scenario: Second pass is a no-op
- GIVEN a file produced by a first run of standardization
- WHEN standardization runs again on that file
- THEN the resulting file is byte-identical to the input

### Requirement: Re-indexing
After any reshaping, the standardized output SHALL have cues indexed sequentially from `1`, with no gaps or duplicates.

#### Scenario: Indices after splitting
- GIVEN standardization splits cue 5 into two cues
- WHEN the output is written
- THEN the resulting file is renumbered so all indices are sequential and 1-based
