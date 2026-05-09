package improve

import (
	"math"
	"regexp"
	"strings"
	"unicode"

	"video-to-srt/internal/srt"
)

const (
	MaxDurationMS = 7000
	MinDurationMS = 500
	MaxCPS        = 17
	MaxChars      = 84
	LineWidth     = 42
	MinGapMS      = 80
)

func DisplayedLen(text string) int { return len(strings.ReplaceAll(text, "\n", "")) }

func WrapText(text string, firstWidth int) string {
	oneLine := strings.Join(strings.Fields(text), " ")
	if firstWidth <= 0 {
		firstWidth = LineWidth
	}
	if len(oneLine) <= firstWidth {
		return oneLine
	}
	if idx, ok := bestLineBreak(oneLine, firstWidth); ok {
		return strings.TrimRightFunc(oneLine[:idx], unicode.IsSpace) + "\n" + strings.TrimLeftFunc(oneLine[idx:], unicode.IsSpace)
	}
	lines := wrapWords(oneLine, firstWidth)
	if len(lines) <= 1 {
		return oneLine
	}
	return lines[0] + "\n" + strings.Join(wrapWords(strings.Join(lines[1:], " "), LineWidth), "\n")
}

func bestLineBreak(text string, firstWidth int) (int, bool) {
	candidates := []int{}
	for _, re := range []*regexp.Regexp{
		regexp.MustCompile(`[,.!?;:]\s+`),
		regexp.MustCompile(`(?i)\s+(and|but|or|because|so|yet)\s+`),
		regexp.MustCompile(`\s+`),
	} {
		for _, loc := range re.FindAllStringIndex(text, -1) {
			idx := loc[0]
			if strings.ContainsAny(text[loc[0]:loc[1]], ",.!?;:") {
				idx = loc[0] + 1
			}
			if idx <= firstWidth && len(strings.TrimSpace(text[idx:])) <= LineWidth {
				candidates = append(candidates, idx)
			}
		}
	}
	if len(candidates) == 0 {
		return 0, false
	}
	best := candidates[0]
	for _, idx := range candidates[1:] {
		if math.Abs(float64(idx)-float64(len(text))/2) < math.Abs(float64(best)-float64(len(text))/2) {
			best = idx
		}
	}
	return best, true
}

func wrapWords(text string, width int) []string {
	words := strings.Fields(text)
	if len(words) == 0 {
		return nil
	}
	lines := []string{words[0]}
	for _, word := range words[1:] {
		last := len(lines) - 1
		if len(lines[last])+1+len(word) <= width {
			lines[last] += " " + word
		} else {
			lines = append(lines, word)
		}
	}
	return lines
}

func splitWords(text string) []string { return strings.Fields(strings.ReplaceAll(text, "\n", " ")) }

func chooseSplit(words []string, maxChars int) int {
	best, current := 1, 0
	for i, word := range words {
		current += len(word)
		if i > 0 {
			current++
		}
		if current > maxChars {
			break
		}
		best = i + 1
	}
	lo := max(1, best-6)
	hi := min(len(words), best+6)
	for _, marks := range []string{".?!", ",;:"} {
		marked := 0
		for i := lo; i <= hi; i++ {
			if strings.ContainsRune(marks, []rune(strings.TrimRight(words[i-1], " \t\n\r"))[len([]rune(strings.TrimRight(words[i-1], " \t\n\r")))-1]) {
				marked = i
			}
		}
		if marked > 0 {
			return marked
		}
	}
	return best
}

func SplitLongCue(cue srt.Cue) []srt.Cue {
	pending := splitWords(cue.Text)
	if len(pending) == 0 {
		return nil
	}
	cueLimit := MaxChars
	firstWidth := LineWidth
	if cue.Speaker != "" {
		prefix := len(cue.Speaker) + 2
		cueLimit = max(20, MaxChars-prefix)
		firstWidth = max(10, LineWidth-prefix)
	}
	parts := []string{}
	for len(pending) > 0 {
		splitAt := len(pending)
		text := strings.Join(pending, " ")
		durationOK := cue.DurationMS() <= MaxDurationMS
		charsOK := len(text) <= cueLimit
		cpsOK := cue.DurationMS() <= 0 || float64(DisplayedLen(text))*1000/float64(cue.DurationMS()) <= MaxCPS
		if !(durationOK && charsOK && cpsOK) && len(pending) > 1 {
			maxChars := min(cueLimit, max(1, MaxCPS*MaxDurationMS/1000))
			if cue.DurationMS() > MaxDurationMS {
				maxChars = min(maxChars, max(1, int(math.Floor(float64(len(text))*float64(MaxDurationMS)/float64(cue.DurationMS())))))
			}
			splitAt = chooseSplit(pending, maxChars)
		}
		for splitAt > 1 && len(strings.Split(WrapText(strings.Join(pending[:splitAt], " "), firstWidth), "\n")) > 2 {
			splitAt--
		}
		parts = append(parts, strings.Join(pending[:splitAt], " "))
		pending = pending[splitAt:]
	}
	totalChars := 0
	for _, part := range parts {
		totalChars += max(1, DisplayedLen(part))
	}
	result := []srt.Cue{}
	cursor := cue.StartMS
	for i, part := range parts {
		end := cue.EndMS
		if i != len(parts)-1 {
			share := float64(max(1, DisplayedLen(part))) / float64(totalChars)
			end = min(cue.EndMS, cursor+max(MinDurationMS, int(math.Round(float64(cue.DurationMS())*share))))
		}
		copy := cue
		copy.StartMS = cursor
		copy.EndMS = max(cursor+MinDurationMS, min(cursor+MaxDurationMS, end))
		if i == len(parts)-1 {
			copy.EndMS = max(cursor+MinDurationMS, end)
		}
		copy.Text = WrapText(part, firstWidth)
		result = append(result, copy)
		cursor = copy.EndMS
	}
	return result
}

func ExtendForCPS(cues []srt.Cue) []srt.Cue {
	result := append([]srt.Cue(nil), cues...)
	for i, cue := range result {
		cps := float64(DisplayedLen(cue.Text)) * 1000 / float64(max(1, cue.DurationMS()))
		if cps <= MaxCPS {
			continue
		}
		requiredEnd := cue.StartMS + int(math.Round(float64(DisplayedLen(cue.Text))*1000/MaxCPS))
		nextStart := requiredEnd
		if i+1 < len(result) {
			nextStart = result[i+1].StartMS - MinGapMS
		}
		result[i].EndMS = max(cue.EndMS, min(requiredEnd, nextStart))
	}
	return result
}

func EnforceGaps(cues []srt.Cue) []srt.Cue {
	result := append([]srt.Cue(nil), cues...)
	for i := 0; i < len(result)-1; i++ {
		current, next := result[i], result[i+1]
		if next.StartMS-current.EndMS >= MinGapMS {
			continue
		}
		if targetEnd := next.StartMS - MinGapMS; targetEnd-current.StartMS >= MinDurationMS {
			result[i].EndMS = targetEnd
			continue
		}
		if targetStart := current.EndMS + MinGapMS; next.EndMS-targetStart >= MinDurationMS {
			result[i+1].StartMS = targetStart
			continue
		}
		if next.StartMS < current.EndMS {
			result[i].EndMS = max(current.StartMS+1, next.StartMS)
		}
	}
	return result
}

func ImproveCues(cues []srt.Cue) []srt.Cue {
	valid := []srt.Cue{}
	for _, cue := range cues {
		if cue.EndMS > cue.StartMS {
			valid = append(valid, cue)
		}
	}
	valid = SplitEmbeddedSpeakerChanges(valid)
	speakers := map[string]bool{}
	for _, cue := range valid {
		if cue.Speaker != "" {
			speakers[cue.Speaker] = true
		}
	}
	multiSpeaker := len(speakers) >= 2
	improved := []srt.Cue{}
	for _, cue := range valid {
		base := cue
		if !multiSpeaker {
			base.Speaker = ""
		}
		base.Text = strings.Join(strings.Fields(cue.Text), " ")
		improved = append(improved, SplitLongCue(base)...)
	}
	improved = ExtendForCPS(improved)
	improved = EnforceGaps(improved)
	out := []srt.Cue{}
	for _, cue := range improved {
		if strings.TrimSpace(cue.Text) == "" {
			continue
		}
		cue.Text = WrapCueText(cue)
		out = append(out, cue)
	}
	return srt.Reindex(out)
}

func WrapCueText(cue srt.Cue) string {
	firstWidth := LineWidth
	if cue.Speaker != "" {
		firstWidth = max(10, LineWidth-len(cue.Speaker)-2)
	}
	return WrapText(cue.Text, firstWidth)
}

func SplitEmbeddedSpeakerChanges(cues []srt.Cue) []srt.Cue {
	marker := regexp.MustCompile(`\b(Speaker\s+[^:]+):`)
	result := []srt.Cue{}
	for _, cue := range cues {
		matches := marker.FindAllStringSubmatchIndex(cue.Text, -1)
		if len(matches) == 0 {
			result = append(result, cue)
			continue
		}
		type piece struct{ speaker, text string }
		pieces := []piece{}
		if strings.TrimSpace(cue.Text[:matches[0][0]]) != "" {
			speaker := cue.Speaker
			if speaker == "" {
				speaker = "Speaker 1"
			}
			pieces = append(pieces, piece{speaker, strings.TrimSpace(cue.Text[:matches[0][0]])})
		}
		for i, match := range matches {
			end := len(cue.Text)
			if i+1 < len(matches) {
				end = matches[i+1][0]
			}
			pieces = append(pieces, piece{cue.Text[match[2]:match[3]], strings.TrimSpace(cue.Text[match[1]:end])})
		}
		filtered := pieces[:0]
		for _, p := range pieces {
			if p.text != "" {
				filtered = append(filtered, p)
			}
		}
		if len(filtered) <= 1 {
			result = append(result, cue)
			continue
		}
		total := 0
		for _, p := range filtered {
			total += max(1, DisplayedLen(p.text))
		}
		cursor := cue.StartMS
		for i, p := range filtered {
			end := cue.EndMS
			if i != len(filtered)-1 {
				end = cursor + int(math.Round(float64(cue.DurationMS()*max(1, DisplayedLen(p.text)))/float64(total)))
			}
			copy := cue
			copy.StartMS, copy.EndMS, copy.Speaker, copy.Text = cursor, end, p.speaker, p.text
			result = append(result, copy)
			cursor = end
		}
	}
	return result
}

func ImproveFile(inputPath, outputPath string) error {
	cues, err := srt.ParseFile(inputPath)
	if err != nil {
		return err
	}
	if err := srt.AtomicWriteFile(outputPath, ImproveCues(cues)); err != nil {
		return err
	}
	return srt.ValidateFile(outputPath)
}
