package srt

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTimestampFormattingAndParsing(t *testing.T) {
	got, err := MSToTimestamp(3723123)
	if err != nil || got != "01:02:03,123" {
		t.Fatalf("MSToTimestamp() = %q, %v", got, err)
	}
	ms, err := TimestampToMS("01:02:03,123")
	if err != nil || ms != 3723123 {
		t.Fatalf("TimestampToMS() = %d, %v", ms, err)
	}
	if _, err := MSToTimestamp(-1); err == nil {
		t.Fatal("expected negative timestamp error")
	}
}

func TestFormatReindexesSpeakerAndEmptyOutput(t *testing.T) {
	out, err := Format([]Cue{{Index: 9, StartMS: 1000, EndMS: 2500, Speaker: "Speaker 2", Text: "hello"}})
	if err != nil {
		t.Fatal(err)
	}
	want := "1\n00:00:01,000 --> 00:00:02,500\nSpeaker 2: hello\n"
	if out != want {
		t.Fatalf("Format() = %q, want %q", out, want)
	}
	empty, err := Format(nil)
	if err != nil || empty != "" {
		t.Fatalf("empty Format() = %q, %v", empty, err)
	}
}

func TestParseRejectsEncodingAndMalformedInputs(t *testing.T) {
	dir := t.TempDir()
	cases := map[string][]byte{
		"bom.srt":       append([]byte{0xef, 0xbb, 0xbf}, []byte("1\n00:00:00,000 --> 00:00:01,000\nHi\n")...),
		"crlf.srt":      []byte("1\r\n00:00:00,000 --> 00:00:01,000\r\nHi\r\n"),
		"utf8.srt":      {0xff, 0xfe},
		"nonewline.srt": []byte("1\n00:00:00,000 --> 00:00:01,000\nHi"),
		"malformed.srt": []byte("1\n00:00:00,000 --> 00:00:01,000\n"),
		"timing.srt":    []byte("1\n00:00:00.000 --> 00:00:01,000\nHi\n"),
		"empty.srt":     []byte("1\n00:00:00,000 --> 00:00:01,000\n   \n"),
	}
	for name, data := range cases {
		path := filepath.Join(dir, name)
		if err := os.WriteFile(path, data, 0o644); err != nil {
			t.Fatal(err)
		}
		if _, err := ParseFile(path); err == nil {
			t.Fatalf("ParseFile(%s) succeeded, want error", name)
		}
	}
}

func TestParseValidAndSpeakerPrefix(t *testing.T) {
	cues, err := Parse("1\n00:00:00,000 --> 00:00:01,000\nSpeaker 1: Hello\nworld\n\n2\n00:00:01,000 --> 00:00:02,000\nBye\n")
	if err != nil {
		t.Fatal(err)
	}
	if len(cues) != 2 || cues[0].Speaker != "Speaker 1" || cues[0].Text != "Hello\nworld" {
		t.Fatalf("unexpected cues: %#v", cues)
	}
}

func TestValidateAndPureCheck(t *testing.T) {
	dir := t.TempDir()
	valid := filepath.Join(dir, "valid.srt")
	data := []byte("1\n00:00:00,000 --> 00:00:01,000\nHi\n\n2\n00:00:01,000 --> 00:00:02,000\nBye\n")
	if err := os.WriteFile(valid, data, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := ValidateFile(valid); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(valid)
	if string(after) != string(data) {
		t.Fatal("ValidateFile mutated input")
	}
	badCases := [][]Cue{
		{{Index: 2, StartMS: 0, EndMS: 1000, Text: "bad index"}},
		{{Index: 1, StartMS: 0, EndMS: 0, Text: "zero"}},
		{{Index: 1, StartMS: 0, EndMS: 1000, Text: "one"}, {Index: 2, StartMS: 900, EndMS: 1200, Text: "overlap"}},
	}
	for _, cues := range badCases {
		if err := ValidateCues(cues); err == nil || !strings.Contains(err.Error(), "cue") && !strings.Contains(err.Error(), "index") {
			t.Fatalf("ValidateCues(%#v) = %v", cues, err)
		}
	}
}
