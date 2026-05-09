package srt

import (
	"bytes"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"
)

type Cue struct {
	Index   int
	StartMS int
	EndMS   int
	Text    string
	Speaker string
}

func (c Cue) DurationMS() int { return c.EndMS - c.StartMS }

type Error string

func (e Error) Error() string { return string(e) }

var timingRE = regexp.MustCompile(`^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$`)
var timestampRE = regexp.MustCompile(`^(\d{2}):(\d{2}):(\d{2}),(\d{3})$`)
var speakerRE = regexp.MustCompile(`^(Speaker\s+[^:]+):\s*(.*)$`)

func TimestampToMS(value string) (int, error) {
	m := timestampRE.FindStringSubmatch(value)
	if m == nil {
		return 0, Error("invalid timestamp: " + value)
	}
	parts := make([]int, 4)
	for i := range parts {
		parts[i], _ = strconv.Atoi(m[i+1])
	}
	if parts[1] >= 60 || parts[2] >= 60 {
		return 0, Error("invalid timestamp range: " + value)
	}
	return ((parts[0]*60+parts[1])*60+parts[2])*1000 + parts[3], nil
}

func MSToTimestamp(value int) (string, error) {
	if value < 0 {
		return "", Error("timestamp cannot be negative")
	}
	seconds := value / 1000
	millis := value % 1000
	minutes := seconds / 60
	seconds %= 60
	hours := minutes / 60
	minutes %= 60
	return fmt.Sprintf("%02d:%02d:%02d,%03d", hours, minutes, seconds, millis), nil
}

func ParseTiming(line string) (int, int, error) {
	if !timingRE.MatchString(line) {
		return 0, 0, Error("invalid timing line: " + line)
	}
	parts := strings.SplitN(line, " --> ", 2)
	start, err := TimestampToMS(parts[0])
	if err != nil {
		return 0, 0, err
	}
	end, err := TimestampToMS(parts[1])
	if err != nil {
		return 0, 0, err
	}
	return start, end, nil
}

func ReadBytes(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	if bytes.HasPrefix(data, []byte{0xef, 0xbb, 0xbf}) {
		return "", Error("file must be UTF-8 without BOM")
	}
	if bytes.Contains(data, []byte("\r\n")) || bytes.Contains(data, []byte("\r")) {
		return "", Error("file must use LF line endings, not CRLF")
	}
	if !utf8.Valid(data) {
		return "", Error("file must be valid UTF-8")
	}
	return string(data), nil
}

func ParseFile(path string) ([]Cue, error) {
	content, err := ReadBytes(path)
	if err != nil {
		return nil, err
	}
	return Parse(content)
}

func Parse(content string) ([]Cue, error) {
	if strings.TrimSpace(content) == "" {
		return []Cue{}, nil
	}
	if !strings.HasSuffix(content, "\n") {
		return nil, Error("file must end with a newline")
	}
	cues := []Cue{}
	offset := 0
	for _, block := range strings.Split(strings.TrimRight(content, "\n"), "\n\n") {
		lineNo := strings.Count(content[:offset], "\n") + 1
		offset += len(block) + 2
		lines := strings.Split(block, "\n")
		if len(lines) < 3 {
			return nil, Error(fmt.Sprintf("malformed cue at line %d", lineNo))
		}
		if _, err := strconv.Atoi(lines[0]); err != nil || lines[0] == "" {
			return nil, Error(fmt.Sprintf("missing numeric index at line %d", lineNo))
		}
		idx, _ := strconv.Atoi(lines[0])
		start, end, err := ParseTiming(lines[1])
		if err != nil {
			return nil, Error(fmt.Sprintf("%v at line %d", err, lineNo+1))
		}
		textLines := lines[2:]
		nonEmpty := false
		for _, line := range textLines {
			if strings.TrimSpace(line) != "" {
				nonEmpty = true
			}
		}
		if !nonEmpty {
			return nil, Error(fmt.Sprintf("empty cue text at line %d", lineNo+2))
		}
		speaker, text := SplitSpeakerPrefix(strings.TrimSpace(strings.Join(textLines, "\n")))
		cues = append(cues, Cue{Index: idx, StartMS: start, EndMS: end, Text: text, Speaker: speaker})
	}
	return cues, nil
}

func SplitSpeakerPrefix(text string) (string, string) {
	first, rest, hasRest := strings.Cut(text, "\n")
	m := speakerRE.FindStringSubmatch(strings.TrimSpace(first))
	if m == nil {
		return "", text
	}
	body := m[2]
	if hasRest {
		body = strings.TrimSpace(body + "\n" + rest)
	}
	return m[1], body
}

func Format(cues []Cue) (string, error) {
	blocks := []string{}
	for i, cue := range cues {
		start, err := MSToTimestamp(cue.StartMS)
		if err != nil {
			return "", err
		}
		end, err := MSToTimestamp(cue.EndMS)
		if err != nil {
			return "", err
		}
		text := strings.TrimSpace(cue.Text)
		if cue.Speaker != "" {
			lines := strings.Split(text, "\n")
			if lines[0] == "" {
				lines[0] = cue.Speaker + ":"
			} else {
				lines[0] = cue.Speaker + ": " + lines[0]
			}
			text = strings.Join(lines, "\n")
		}
		blocks = append(blocks, strings.Join([]string{strconv.Itoa(i + 1), start + " --> " + end, text}, "\n"))
	}
	if len(blocks) == 0 {
		return "", nil
	}
	return strings.Join(blocks, "\n\n") + "\n", nil
}

func WriteFile(path string, cues []Cue) error {
	out, err := Format(cues)
	if err != nil {
		return err
	}
	return os.WriteFile(path, []byte(out), 0o644)
}

func Reindex(cues []Cue) []Cue {
	out := append([]Cue(nil), cues...)
	for i := range out {
		out[i].Index = i + 1
	}
	return out
}
