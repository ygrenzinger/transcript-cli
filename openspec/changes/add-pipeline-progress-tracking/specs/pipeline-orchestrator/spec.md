## MODIFIED Requirements

### Requirement: Stage progress reporting
The orchestrator SHALL report structured progress events to stderr so that the user can follow a long-running pipeline without interactive prompts or external tools. For each pipeline stage, the orchestrator SHALL emit a start event and either a completion event or a failure event. Each progress event SHALL include the current stage number, total stage count, stage name, and status. Progress output SHALL include relevant context when available, such as the selected transcription provider/model and produced artifact path.

#### Scenario: Progress lines include stage status
- GIVEN the orchestrator is invoked
- WHEN it runs successfully
- THEN it emits progress lines to stderr for all four stages
- AND each stage has a start line and a completion line
- AND each progress line identifies the stage number, total stage count, stage name, and status

#### Scenario: Transcription progress includes provider context
- GIVEN the orchestrator is invoked with provider `grok` and model `grok-transcribe-1`
- WHEN it starts the transcription stage
- THEN the transcription progress line includes the provider name
- AND it includes the resolved or requested model when model information is available

#### Scenario: Failure identifies failed stage
- GIVEN a pipeline stage fails
- WHEN the orchestrator reports the failure
- THEN it emits a failure progress line to stderr for the failed stage
- AND the failure line identifies the failed stage name and status
- AND it does not emit start or completion progress for later stages

#### Scenario: Progress uses stderr
- GIVEN the orchestrator is invoked from a script
- WHEN it emits progress updates
- THEN progress updates are written to stderr
- AND stdout is not required for progress reporting
