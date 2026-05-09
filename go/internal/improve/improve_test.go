package improve

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"video-to-srt/internal/srt"
)

func TestWrapTextPrefersPunctuationAndNormalizesWhitespace(t *testing.T) {
	got := WrapText("hello, world this wraps", 20)
	if got != "hello, world\nthis wraps" {
		t.Fatalf("WrapText() = %q", got)
	}
	if strings.Contains(WrapText("a    b\n c", 42), "  ") {
		t.Fatal("WrapText did not normalize whitespace")
	}
}

func TestSplitLongCueDurationCharsCPSAndBoundaries(t *testing.T) {
	cue := srt.Cue{Index: 1, StartMS: 0, EndMS: 14000, Text: "This sentence should split. This second sentence is also long enough to create another subtitle cue with readable text."}
	parts := SplitLongCue(cue)
	if len(parts) < 2 {
		t.Fatalf("SplitLongCue produced %d parts", len(parts))
	}
	for _, part := range parts {
		if part.DurationMS() > MaxDurationMS || DisplayedLen(part.Text) > MaxChars || len(strings.Split(part.Text, "\n")) > 2 {
			t.Fatalf("part violates limits: %#v", part)
		}
	}
}

func TestSpeakerGapFilteringAndIdempotence(t *testing.T) {
	cues := []srt.Cue{
		{Index: 1, StartMS: 0, EndMS: 0, Text: "remove"},
		{Index: 2, StartMS: 0, EndMS: 1000, Text: "Speaker 1: hello Speaker 2: bonjour"},
		{Index: 3, StartMS: 1000, EndMS: 1800, Speaker: "Speaker 2", Text: "touching cue"},
	}
	improved := ImproveCues(cues)
	if len(improved) < 2 {
		t.Fatalf("expected speaker split, got %#v", improved)
	}
	if improved[0].Index != 1 || improved[0].Speaker == "" || improved[1].Speaker == "" {
		t.Fatalf("expected reindexed multi-speaker output: %#v", improved)
	}
	for i := 0; i < len(improved)-1; i++ {
		if improved[i+1].StartMS-improved[i].EndMS < MinGapMS && improved[i].DurationMS() >= MinDurationMS && improved[i+1].DurationMS() >= MinDurationMS {
			t.Fatalf("gap not enforced: %#v", improved)
		}
	}
	second := ImproveCues(improved)
	firstBytes, _ := srt.Format(improved)
	secondBytes, _ := srt.Format(second)
	if firstBytes != secondBytes {
		t.Fatalf("not idempotent:\n%s\n---\n%s", firstBytes, secondBytes)
	}
}

func TestImproveFileKeepsInputAndValidatesOutput(t *testing.T) {
	dir := t.TempDir()
	in := filepath.Join(dir, "in.srt")
	out := filepath.Join(dir, "out.srt")
	data := []byte("1\n00:00:00,000 --> 00:00:01,000\nHello world\n")
	if err := os.WriteFile(in, data, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := ImproveFile(in, out); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(in)
	if string(after) != string(data) {
		t.Fatal("input mutated")
	}
	if err := srt.ValidateFile(out); err != nil {
		t.Fatal(err)
	}
}
