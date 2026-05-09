package pipeline

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"video-to-srt/internal/audio"
	"video-to-srt/internal/improve"
	"video-to-srt/internal/provider"
	"video-to-srt/internal/source"
	"video-to-srt/internal/srt"
)

type Options struct {
	VideoPath string
	Provider  string
	Model     string
	Language  string
	Improve   bool
	Output    string
}

type Dependencies struct {
	Registry *provider.Registry
	Audio    func(context.Context, string, string) (string, error)
	Resolve  func(context.Context, string) (string, error)
	Sleep    provider.Sleeper
	Stderr   io.Writer
}

func Run(ctx context.Context, opts Options, deps Dependencies) (string, error) {
	registry := deps.Registry
	if registry == nil {
		registry = provider.DefaultRegistry()
	}
	selected, resolvedModel, err := registry.ValidateReady(opts.Provider, opts.Model, os.Getenv)
	if err != nil {
		return "", err
	}
	resolve := deps.Resolve
	if resolve == nil {
		resolve = func(ctx context.Context, input string) (string, error) {
			return source.Resolve(ctx, input, nil)
		}
	}
	videoPath, err := resolve(ctx, opts.VideoPath)
	if err != nil {
		return "", err
	}
	rawSRT := withProviderSuffix(videoPath, selected.Metadata().Name, "raw")
	improvedSRT := opts.Output
	if improvedSRT == "" {
		improvedSRT = withProviderSuffix(videoPath, selected.Metadata().Name, "improved")
	}
	total := 2
	if opts.Improve {
		total = 3
	}
	stderr := deps.Stderr
	if stderr == nil {
		stderr = os.Stderr
	}
	extract := deps.Audio
	if extract == nil {
		extract = func(ctx context.Context, video, output string) (string, error) {
			return audio.Extract(ctx, video, output, nil)
		}
	}
	audioPath, err := runStage(stderr, Stage{1, total, "extract_audio", map[string]any{"input": videoPath}}, func() (string, error) {
		return extract(ctx, videoPath, "")
	}, map[string]any{"artifact": audio.DefaultOutputPath(videoPath)})
	if err != nil {
		return "", err
	}
	transcriptionContext := map[string]any{"provider": selected.Metadata().Name, "model": resolvedModel, "input": audioPath}
	if opts.Model != "" {
		transcriptionContext["requested_model"] = opts.Model
	}
	_, err = runStage(stderr, Stage{2, total, "transcribe", transcriptionContext}, func() (struct{}, error) {
		return struct{}{}, provider.TranscribeWithRetries(ctx, selected, audioPath, rawSRT, opts.Model, opts.Language, deps.Sleep)
	}, map[string]any{"artifact": rawSRT})
	if err != nil {
		return "", err
	}
	_ = os.Remove(audioPath)
	if !opts.Improve {
		return rawSRT, nil
	}
	_, err = runStage(stderr, Stage{3, total, "improve_subtitles", map[string]any{"input": rawSRT}}, func() (struct{}, error) {
		if err := improve.ImproveFile(rawSRT, improvedSRT); err != nil {
			return struct{}{}, err
		}
		return struct{}{}, srt.ValidateFile(improvedSRT)
	}, map[string]any{"artifact": improvedSRT})
	if err != nil {
		return "", err
	}
	return improvedSRT, nil
}

type Stage struct {
	Number  int
	Total   int
	Name    string
	Context map[string]any
}

func runStage[T any](w io.Writer, stage Stage, action func() (T, error), done map[string]any) (T, error) {
	var zero T
	EmitProgress(w, stage, "START", nil)
	result, err := action()
	if err != nil {
		EmitProgress(w, stage, "FAIL", map[string]any{"error": fmt.Sprintf("%T", err)})
		return zero, err
	}
	EmitProgress(w, stage, "DONE", done)
	return result, nil
}

func EmitProgress(w io.Writer, stage Stage, status string, extra map[string]any) {
	fields := []struct {
		key   string
		value any
	}{{"stage", fmt.Sprintf("%d/%d", stage.Number, stage.Total)}, {"name", stage.Name}, {"status", status}}
	for _, key := range sortedKeys(stage.Context) {
		fields = append(fields, struct {
			key   string
			value any
		}{key, stage.Context[key]})
	}
	for _, key := range sortedKeys(extra) {
		fields = append(fields, struct {
			key   string
			value any
		}{key, extra[key]})
	}
	parts := []string{}
	for _, field := range fields {
		parts = append(parts, fmt.Sprintf("%s=%s", field.key, formatProgressValue(field.value)))
	}
	fmt.Fprintln(w, "PROGRESS "+strings.Join(parts, " "))
}

func formatProgressValue(value any) string {
	escaped := strings.ReplaceAll(fmt.Sprint(value), `\`, `\\`)
	escaped = strings.ReplaceAll(escaped, `"`, `\"`)
	return `"` + escaped + `"`
}

func sortedKeys(m map[string]any) []string {
	keys := []string{}
	for key := range m {
		keys = append(keys, key)
	}
	// Preserve Python insertion order for known context keys, then append any extras.
	order := map[string]int{"provider": 0, "model": 1, "input": 2, "requested_model": 3, "artifact": 4, "error": 5}
	for i := 0; i < len(keys); i++ {
		for j := i + 1; j < len(keys); j++ {
			if orderValue(keys[j], order) < orderValue(keys[i], order) {
				keys[i], keys[j] = keys[j], keys[i]
			}
		}
	}
	return keys
}

func orderValue(key string, order map[string]int) int {
	if v, ok := order[key]; ok {
		return v
	}
	return 1000 + len(key)
}

func withProviderSuffix(videoPath, providerName, kind string) string {
	ext := filepath.Ext(videoPath)
	return strings.TrimSuffix(videoPath, ext) + "." + providerName + "." + kind + ".srt"
}
