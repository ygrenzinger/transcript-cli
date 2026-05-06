# srt-validation Specification

## Purpose
Verify that an SRT file is structurally well-formed before it is delivered to the user. Validation is concerned with **format correctness** (parseability, ordering, encoding) and not with stylistic best-practices like reading speed or line length — those belong to `srt-standardization`.

## Requirements

### Requirement: Parseability
The validator SHALL parse the SRT file end-to-end and reject any file that does not conform to the SubRip block structure (index line, timing line, one or more text lines, blank-line separator).

#### Scenario: Valid SRT file
- GIVEN a file containing well-formed SRT cue blocks separated by blank lines
- WHEN the validator runs
- THEN it reports the file as valid and exits with a zero status

#### Scenario: Malformed block
- GIVEN a file where a cue is missing its index line, timing line, or trailing blank line
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the offending cue's line number

### Requirement: Sequential indices
Cue indices SHALL be 1-based and strictly increasing by 1, with no gaps or duplicates.

#### Scenario: Correct indices
- GIVEN an SRT containing cues numbered `1`, `2`, `3`, …
- WHEN the validator runs
- THEN it accepts the file

#### Scenario: Index gap or duplicate
- GIVEN an SRT containing cues numbered `1`, `2`, `4` (gap) or `1`, `2`, `2` (duplicate)
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the bad index

### Requirement: Timestamp format
Every timing line SHALL match the form `HH:MM:SS,mmm --> HH:MM:SS,mmm` exactly: two-digit hours/minutes/seconds, three-digit milliseconds, comma decimal separator, ` --> ` arrow with a single space on each side.

#### Scenario: Correct timestamp
- GIVEN a timing line `00:01:05,123 --> 00:01:10,456`
- WHEN the validator runs
- THEN it accepts the line

#### Scenario: Period instead of comma
- GIVEN a timing line `00:01:05.123 --> 00:01:10.456`
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the formatting error

#### Scenario: Missing leading zeros
- GIVEN a timing line `0:1:5,123 --> 0:1:10,456`
- WHEN the validator runs
- THEN it exits with a non-zero status

### Requirement: Monotonic and non-overlapping cues
For every pair of consecutive cues, the start time of cue N+1 SHALL be greater than or equal to the end time of cue N. A cue's end time SHALL be strictly greater than its start time.

#### Scenario: Overlapping cues
- GIVEN cue 1 ends at `00:00:10,000` and cue 2 starts at `00:00:09,500`
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the overlap

#### Scenario: Zero-duration cue
- GIVEN a cue whose start and end timestamps are equal
- WHEN the validator runs
- THEN it exits with a non-zero status

### Requirement: Encoding
The file SHALL be UTF-8 encoded with no byte-order mark, and SHALL use `\n` line endings (not `\r\n`).

#### Scenario: UTF-8 with BOM
- GIVEN a file beginning with the bytes `EF BB BF`
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the BOM

#### Scenario: CRLF line endings
- GIVEN a file using `\r\n` line endings
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the encoding mismatch

### Requirement: Non-empty cue text
Every cue SHALL contain at least one non-whitespace text line.

#### Scenario: Empty cue body
- GIVEN a cue whose text section is empty or contains only whitespace
- WHEN the validator runs
- THEN it exits with a non-zero status and reports the empty cue

### Requirement: Validation as a pure check
The validator SHALL NOT modify the file. It only reads and reports.

#### Scenario: No side effects
- GIVEN any input SRT file
- WHEN the validator runs
- THEN the file's bytes on disk are unchanged regardless of whether validation passes or fails
