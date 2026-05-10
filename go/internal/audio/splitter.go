package audio

import (
	"bytes"
	"context"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"video-to-srt/internal/srt"
)

type SplitterConfig struct {
	TargetChunkDuration int
	OverlapDuration     int
	SilenceThresholdDB  int
	SilenceMinDuration  float64
	SearchWindow        int
	SimilarityThreshold float64
}

func DefaultSplitterConfig() SplitterConfig {
	return SplitterConfig{TargetChunkDuration: 1800, OverlapDuration: 45, SilenceThresholdDB: -30, SilenceMinDuration: 0.5, SearchWindow: 180, SimilarityThreshold: 0.8}
}

func (c SplitterConfig) Validate() error {
	if c.TargetChunkDuration <= 0 {
		return fmt.Errorf("target chunk duration must be greater than zero")
	}
	if c.OverlapDuration < 0 {
		return fmt.Errorf("overlap duration cannot be negative")
	}
	if c.OverlapDuration >= c.TargetChunkDuration {
		return fmt.Errorf("overlap duration must be less than target chunk duration")
	}
	if c.SilenceMinDuration <= 0 {
		return fmt.Errorf("minimum silence duration must be greater than zero")
	}
	if c.SearchWindow <= 0 {
		return fmt.Errorf("search window must be greater than zero")
	}
	if c.SimilarityThreshold < 0 || c.SimilarityThreshold > 1 {
		return fmt.Errorf("similarity threshold must be between 0 and 1")
	}
	return nil
}

type SilencePoint struct{ Start, End, Duration float64 }

func (s SilencePoint) Center() float64 { return (s.Start + s.End) / 2 }

type Chunk struct {
	Path         string
	Index        int
	StartTime    float64
	EndTime      float64
	OverlapStart float64
	OverlapEnd   float64
}

type SplitCommandRunner interface {
	Run(ctx context.Context, name string, args ...string) error
	Output(ctx context.Context, name string, args ...string) ([]byte, error)
}

type ExecSplitRunner struct{}

func (ExecSplitRunner) Run(ctx context.Context, name string, args ...string) error {
	return exec.CommandContext(ctx, name, args...).Run()
}

func (ExecSplitRunner) Output(ctx context.Context, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	return cmd.CombinedOutput()
}

type Splitter struct {
	Config SplitterConfig
	Runner SplitCommandRunner
}

func NewSplitter(config SplitterConfig, runner SplitCommandRunner) (Splitter, error) {
	if config == (SplitterConfig{}) {
		config = DefaultSplitterConfig()
	}
	if err := config.Validate(); err != nil {
		return Splitter{}, err
	}
	if runner == nil {
		runner = ExecSplitRunner{}
	}
	return Splitter{Config: config, Runner: runner}, nil
}

func (s Splitter) Duration(ctx context.Context, audioPath string) (float64, error) {
	out, err := s.Runner.Output(ctx, "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audioPath)
	if err != nil {
		return 0, fmt.Errorf("audio duration probe failed: %w", err)
	}
	duration, err := strconv.ParseFloat(strings.TrimSpace(string(out)), 64)
	if err != nil {
		return 0, fmt.Errorf("audio duration probe failed: %w", err)
	}
	return duration, nil
}

func (s Splitter) DetectSilences(ctx context.Context, audioPath string) ([]SilencePoint, error) {
	filter := fmt.Sprintf("silencedetect=noise=%ddB:d=%g", s.Config.SilenceThresholdDB, s.Config.SilenceMinDuration)
	out, err := s.Runner.Output(ctx, "ffmpeg", "-i", audioPath, "-af", filter, "-f", "null", "-")
	if err != nil {
		return nil, fmt.Errorf("silence detection failed: %w", err)
	}
	return ParseSilenceDetectOutput(string(out)), nil
}

func (s Splitter) SplitPoints(duration float64, silences []SilencePoint) []float64 {
	points := []float64{}
	target := float64(s.Config.TargetChunkDuration)
	for target < duration-float64(s.Config.TargetChunkDuration)/2 {
		windowStart := target - float64(s.Config.SearchWindow)
		windowEnd := target + float64(s.Config.SearchWindow)
		candidates := []SilencePoint{}
		for _, silence := range silences {
			if silence.Center() >= windowStart && silence.Center() <= windowEnd {
				candidates = append(candidates, silence)
			}
		}
		split := target
		if len(candidates) > 0 {
			sort.Slice(candidates, func(i, j int) bool {
				return s.silenceScore(candidates[i], target) > s.silenceScore(candidates[j], target)
			})
			split = candidates[0].Center()
		}
		points = append(points, split)
		target = split + float64(s.Config.TargetChunkDuration)
	}
	return points
}

func (s Splitter) Split(ctx context.Context, audioPath, outputDir string) ([]Chunk, error) {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return nil, err
	}
	duration, err := s.Duration(ctx, audioPath)
	if err != nil {
		return nil, err
	}
	if duration <= float64(s.Config.TargetChunkDuration)+float64(s.Config.TargetChunkDuration)/2 {
		return []Chunk{{Path: audioPath, Index: 0, StartTime: 0, EndTime: duration}}, nil
	}
	logSplit("SILENCE_DETECT", map[string]any{"status": "START", "input": audioPath})
	silenceStart := time.Now()
	silences, err := s.DetectSilences(ctx, audioPath)
	if err != nil {
		return nil, err
	}
	logSplit("SILENCE_DETECT", map[string]any{
		"status":           "DONE",
		"input":            audioPath,
		"silences":         len(silences),
		"duration_seconds": math.Round(time.Since(silenceStart).Seconds()*1000) / 1000,
	})
	points := s.SplitPoints(duration, silences)
	if len(points) == 0 {
		return []Chunk{{Path: audioPath, Index: 0, StartTime: 0, EndTime: duration}}, nil
	}
	boundaries := append([]float64{0}, points...)
	boundaries = append(boundaries, duration)
	total := len(boundaries) - 1
	logSplit("EXTRACT", map[string]any{"status": "START", "chunks": total})
	extractStart := time.Now()
	chunks := []Chunk{}
	for i := 0; i < total; i++ {
		start := boundaries[i]
		end := boundaries[i+1]
		actualStart := start
		if i > 0 {
			actualStart = math.Max(0, start-float64(s.Config.OverlapDuration))
		}
		actualEnd := end
		if i < len(boundaries)-2 {
			actualEnd = math.Min(duration, end+float64(s.Config.OverlapDuration))
		}
		chunkPath := filepath.Join(outputDir, strings.TrimSuffix(filepath.Base(audioPath), filepath.Ext(audioPath))+fmt.Sprintf("_chunk%03d%s", i, filepath.Ext(audioPath)))
		if err := s.ExtractChunk(ctx, audioPath, chunkPath, actualStart, actualEnd); err != nil {
			return nil, err
		}
		logSplit("EXTRACT", map[string]any{"status": "PROGRESS", "index": i + 1, "total": total})
		chunk := Chunk{Path: chunkPath, Index: i, StartTime: actualStart, EndTime: actualEnd}
		if i > 0 {
			chunk.OverlapStart = start - actualStart
		}
		if i < len(boundaries)-2 {
			chunk.OverlapEnd = actualEnd - end
		}
		chunks = append(chunks, chunk)
	}
	logSplit("EXTRACT", map[string]any{
		"status":           "DONE",
		"chunks":           total,
		"duration_seconds": math.Round(time.Since(extractStart).Seconds()*1000) / 1000,
	})
	return chunks, nil
}

func logSplit(event string, fields map[string]any) {
	keys := make([]string, 0, len(fields))
	for k := range fields {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, k := range keys {
		v := fmt.Sprint(fields[k])
		v = strings.ReplaceAll(v, "\\", "\\\\")
		v = strings.ReplaceAll(v, "\"", "\\\"")
		parts = append(parts, fmt.Sprintf("%s=\"%s\"", k, v))
	}
	fmt.Fprintf(os.Stderr, "%s %s\n", event, strings.Join(parts, " "))
}

func (s Splitter) ExtractChunk(ctx context.Context, source, dest string, start, end float64) error {
	if err := s.Runner.Run(ctx, "ffmpeg", "-y", "-i", source, "-ss", fmt.Sprint(start), "-t", fmt.Sprint(end-start), "-c", "copy", dest); err != nil {
		return fmt.Errorf("chunk extraction failed: %w", err)
	}
	return nil
}

func (s Splitter) silenceScore(silence SilencePoint, target float64) float64 {
	distance := math.Abs(silence.Center() - target)
	factor := math.Max(0, 1-distance/float64(s.Config.SearchWindow))
	return silence.Duration * factor
}

var silenceStartRE = regexp.MustCompile(`silence_start:\s*([\d.]+)`)
var silenceEndRE = regexp.MustCompile(`silence_end:\s*([\d.]+)`)

func ParseSilenceDetectOutput(output string) []SilencePoint {
	silences := []SilencePoint{}
	var start float64
	haveStart := false
	for _, line := range strings.Split(output, "\n") {
		if m := silenceStartRE.FindStringSubmatch(line); m != nil {
			start, _ = strconv.ParseFloat(m[1], 64)
			haveStart = true
		} else if haveStart {
			if m := silenceEndRE.FindStringSubmatch(line); m != nil {
				end, _ := strconv.ParseFloat(m[1], 64)
				silences = append(silences, SilencePoint{Start: start, End: end, Duration: end - start})
				haveStart = false
			}
		}
	}
	return silences
}

func OffsetCues(cues []srt.Cue, offsetSeconds float64) []srt.Cue {
	out := append([]srt.Cue(nil), cues...)
	offsetMS := int(math.Round(offsetSeconds * 1000))
	for i := range out {
		out[i].StartMS += offsetMS
		out[i].EndMS += offsetMS
	}
	return out
}

func MergeChunkSRTs(chunks []Chunk, srtPaths []string, outputPath string, similarityThreshold float64) error {
	if len(chunks) != len(srtPaths) {
		return fmt.Errorf("number of chunks and SRT files must match")
	}
	merged := []srt.Cue{}
	for i, chunk := range chunks {
		cues, err := srt.ParseFile(srtPaths[i])
		if err != nil {
			return err
		}
		current := OffsetCues(cues, chunk.StartTime)
		if i == 0 {
			merged = append(merged, current...)
			continue
		}
		keepPrev, useCurr := FindOverlapBoundary(merged, current, chunk.OverlapStart, similarityThreshold)
		merged = append([]srt.Cue(nil), merged[:keepPrev]...)
		merged = append(merged, current[useCurr:]...)
	}
	sort.SliceStable(merged, func(i, j int) bool {
		if merged[i].StartMS == merged[j].StartMS {
			return merged[i].EndMS < merged[j].EndMS
		}
		return merged[i].StartMS < merged[j].StartMS
	})
	return srt.AtomicWriteFile(outputPath, srt.Reindex(merged))
}

func FindOverlapBoundary(prev, curr []srt.Cue, overlapSeconds float64, similarityThreshold float64) (int, int) {
	if len(prev) == 0 || len(curr) == 0 || overlapSeconds <= 0 {
		return len(prev), 0
	}
	overlapMS := int(math.Round(overlapSeconds * 1000))
	overlapStart := prev[len(prev)-1].EndMS - overlapMS
	if overlapStart < 0 {
		overlapStart = 0
	}
	currOverlapEnd := curr[0].StartMS + overlapMS
	bestPrev, bestCurr, bestScore := -1, -1, 0.0
	for i, p := range prev {
		if p.StartMS < overlapStart {
			continue
		}
		for j, c := range curr {
			if c.EndMS > currOverlapEnd {
				continue
			}
			score := TextSimilarity(p.Text, c.Text)
			if score >= similarityThreshold && score > bestScore {
				bestPrev, bestCurr, bestScore = i, j+1, score
			}
		}
	}
	if bestPrev >= 0 {
		return bestPrev, bestCurr
	}
	for i, cue := range prev {
		if cue.StartMS >= overlapStart {
			return i, 0
		}
	}
	return len(prev), 0
}

func TextSimilarity(left, right string) float64 {
	a := []rune(normalizeText(left))
	b := []rune(normalizeText(right))
	if len(a) == 0 && len(b) == 0 {
		return 1
	}
	dist := levenshtein(a, b)
	maxLen := math.Max(float64(len(a)), float64(len(b)))
	return 1 - float64(dist)/maxLen
}

func normalizeText(value string) string {
	return strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(value))), " ")
}

func levenshtein(a, b []rune) int {
	prev := make([]int, len(b)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(a); i++ {
		curr := make([]int, len(b)+1)
		curr[0] = i
		for j := 1; j <= len(b); j++ {
			cost := 0
			if a[i-1] != b[j-1] {
				cost = 1
			}
			curr[j] = min(curr[j-1]+1, prev[j]+1, prev[j-1]+cost)
		}
		prev = curr
	}
	return prev[len(b)]
}

func min(values ...int) int {
	out := values[0]
	for _, value := range values[1:] {
		if value < out {
			out = value
		}
	}
	return out
}

func CombinedOutputError(name string, out []byte, err error) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%s failed: %w: %s", name, err, string(bytes.TrimSpace(out)))
}
