package itf

import (
	"fmt"
)

func Apply(content string, config Config) (map[string][]string, error) {
	app, err := NewApp(&config)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize itf app: %w", err)
	}

	summary, err := app.processAndApply(content)
	if err != nil {
		return nil, err
	}

	return map[string][]string{
		"Created":  summary.Created,
		"Modified": summary.Modified,
		"Renamed":  summary.Renamed,
		"Deleted":  summary.Deleted,
		"Failed":   summary.Failed,
	}, nil
}
