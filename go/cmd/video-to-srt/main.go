package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	"video-to-srt/internal/pipeline"
	"video-to-srt/internal/provider"
)

func main() { os.Exit(run(os.Args[1:])) }

func run(argv []string) int {
	if len(argv) > 0 && (argv[0] == "providers" || argv[0] == "list-providers") {
		out, err := provider.DefaultRegistry().ListJSON()
		if err != nil {
			fmt.Fprintln(os.Stderr, "Error:", err)
			return 1
		}
		fmt.Println(out)
		return 0
	}
	fs := flag.NewFlagSet("video-to-srt", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	providerName := fs.String("provider", "voxtral", "transcription provider")
	model := fs.String("model", "", "provider model")
	language := fs.String("language", "", "language hint")
	improveFlag := fs.Bool("improve-subtitles", false, "write a readability-improved SRT")
	output := fs.String("output", "", "custom improved SRT path; requires --improve-subtitles")
	fs.StringVar(output, "o", "", "custom improved SRT path; requires --improve-subtitles")
	if err := fs.Parse(argv); err != nil {
		return 2
	}
	if fs.NArg() != 1 {
		fmt.Fprintln(os.Stderr, "Error: missing input source")
		return 1
	}
	if *output != "" && !*improveFlag {
		fmt.Fprintln(os.Stderr, "Error: --output requires --improve-subtitles")
		return 1
	}
	input := fs.Arg(0)
	out, err := pipeline.Run(context.Background(), pipeline.Options{VideoPath: input, Provider: *providerName, Model: *model, Language: *language, Improve: *improveFlag, Output: *output}, pipeline.Dependencies{})
	if err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		return 1
	}
	fmt.Fprintln(os.Stderr, "Wrote", out)
	return 0
}
