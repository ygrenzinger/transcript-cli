package audio

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"video-to-srt/internal/srt"
)

type fakeSplitRunner struct {
	outputs map[string][]byte
	runs    [][]string
}

func (f *fakeSplitRunner) Run(ctx context.Context, name string, args ...string) error {
	f.runs = append(f.runs, append([]string{name}, args...))
	return os.WriteFile(args[len(args)-1], []byte("chunk"), 0o644)
}

func (f *fakeSplitRunner) Output(ctx context.Context, name string, args ...string) ([]byte, error) {
	if f.outputs == nil {
		return nil, errors.New("missing output")
	}
	return f.outputs[name], nil
}

func TestSplitterSplitPointsNoSplitAndOverlap(t *testing.T) {
	config := SplitterConfig{TargetChunkDuration: 100, OverlapDuration: 10, SilenceThresholdDB: -30, SilenceMinDuration: 0.5, SearchWindow: 20, SimilarityThreshold: 0.8}
	splitter, err := NewSplitter(config, &fakeSplitRunner{outputs: map[string][]byte{"ffprobe": []byte("260"), "ffmpeg": []byte("silence_start: 98\nsilence_end: 102\nsilence_start: 198\nsilence_end: 202\n")}})
	if err != nil {
		t.Fatal(err)
	}
	points := splitter.SplitPoints(260, []SilencePoint{{Start: 98, End: 102, Duration: 4}})
	if !reflect.DeepEqual(points, []float64{100, 200}) {
		t.Fatalf("points=%v", points)
	}
	dir := t.TempDir()
	audioPath := filepath.Join(dir, "audio.mp3")
	if err := os.WriteFile(audioPath, []byte("audio"), 0o644); err != nil {
		t.Fatal(err)
	}
	chunks, err := splitter.Split(context.Background(), audioPath, filepath.Join(dir, "chunks"))
	if err != nil {
		t.Fatal(err)
	}
	if len(chunks) != 3 || chunks[0].StartTime != 0 || chunks[0].OverlapEnd != 10 || chunks[1].OverlapStart != 10 || chunks[2].EndTime != 260 {
		t.Fatalf("bad chunks: %+v", chunks)
	}

	short, _ := NewSplitter(config, &fakeSplitRunner{outputs: map[string][]byte{"ffprobe": []byte("50"), "ffmpeg": []byte("")}})
	chunks, err = short.Split(context.Background(), audioPath, filepath.Join(dir, "short"))
	if err != nil {
		t.Fatal(err)
	}
	if len(chunks) != 1 || chunks[0].Path != audioPath || chunks[0].StartTime != 0 || chunks[0].EndTime != 50 {
		t.Fatalf("short chunks=%+v", chunks)
	}
}

func TestMergeChunkSRTsOffsetsReindexesAndDeduplicates(t *testing.T) {
	dir := t.TempDir()
	first := filepath.Join(dir, "first.srt")
	second := filepath.Join(dir, "second.srt")
	output := filepath.Join(dir, "merged.srt")
	if err := srt.AtomicWriteFile(first, []srt.Cue{{Index: 1, StartMS: 0, EndMS: 1000, Text: "hello"}, {Index: 2, StartMS: 4000, EndMS: 5000, Text: "same words"}}); err != nil {
		t.Fatal(err)
	}
	if err := srt.AtomicWriteFile(second, []srt.Cue{{Index: 1, StartMS: 0, EndMS: 1000, Text: "same words"}, {Index: 2, StartMS: 2000, EndMS: 3000, Text: "after"}}); err != nil {
		t.Fatal(err)
	}
	chunks := []Chunk{{Path: first, Index: 0, StartTime: 0, EndTime: 5, OverlapEnd: 2}, {Path: second, Index: 1, StartTime: 4, EndTime: 8, OverlapStart: 2}}
	if err := MergeChunkSRTs(chunks, []string{first, second}, output, 0.8); err != nil {
		t.Fatal(err)
	}
	cues, err := srt.ParseFile(output)
	if err != nil {
		t.Fatal(err)
	}
	if got := []string{cues[0].Text, cues[1].Text}; !reflect.DeepEqual(got, []string{"hello", "after"}) {
		t.Fatalf("texts=%v", got)
	}
	if cues[1].StartMS != 6000 || cues[1].Index != 2 {
		t.Fatalf("bad second cue: %+v", cues[1])
	}
}
