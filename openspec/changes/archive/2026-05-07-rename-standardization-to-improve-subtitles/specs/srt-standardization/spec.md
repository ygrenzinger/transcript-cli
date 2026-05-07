## REMOVED Requirements

### Requirement: Invalid raw cue filtering
**Reason**: Replaced by `subtitle-improvement`, which owns filtering invalid raw provider cues before readability cleanup.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Cue duration limits
**Reason**: Replaced by `subtitle-improvement`, which owns readability-oriented cue duration limits.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Reading speed (characters per second)
**Reason**: Replaced by `subtitle-improvement`, which owns reading-speed constraints.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Line and character limits
**Reason**: Replaced by `subtitle-improvement`, which owns line wrapping and cue length constraints.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Boundary preferences
**Reason**: Replaced by `subtitle-improvement`, which owns cue split boundary selection.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Speaker change forces cue boundary
**Reason**: Replaced by `subtitle-improvement`, which owns speaker-aware cue splitting.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Inter-cue gap
**Reason**: Replaced by `subtitle-improvement`, which owns gap enforcement in improved subtitles.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Speaker labeling
**Reason**: Replaced by `subtitle-improvement`, which owns speaker labeling in improved subtitles.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Idempotence
**Reason**: Replaced by `subtitle-improvement`, which owns idempotence for improved subtitle output.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.

### Requirement: Re-indexing
**Reason**: Replaced by `subtitle-improvement`, which owns re-indexing after subtitle cleanup.
**Migration**: Use the `subtitle-improvement` capability and its improved output artifact.
