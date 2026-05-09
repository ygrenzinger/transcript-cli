package srt

import "fmt"

func ValidateFile(path string) error {
	cues, err := ParseFile(path)
	if err != nil {
		return err
	}
	return ValidateCues(cues)
}

func ValidateCues(cues []Cue) error {
	previousEnd := -1
	for i, cue := range cues {
		expected := i + 1
		if cue.Index != expected {
			return Error(fmt.Sprintf("bad cue index %d; expected %d", cue.Index, expected))
		}
		if cue.EndMS <= cue.StartMS {
			return Error(fmt.Sprintf("cue %d end time must be greater than start time", cue.Index))
		}
		if previousEnd >= 0 && cue.StartMS < previousEnd {
			return Error(fmt.Sprintf("cue %d overlaps previous cue", cue.Index))
		}
		previousEnd = cue.EndMS
	}
	return nil
}
