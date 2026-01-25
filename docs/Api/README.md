# API (Library Usage)

`itf` can be integrated into other Go applications as a library to programmatically apply file changes from markdown content.

## Public API

### `Apply`

The primary entry point for the library. It parses the provided markdown content and applies the changes according to the configuration.

```go
func Apply(content string, config Config) (map[string][]string, error)
```

**Returns:**
A map where keys represent the action performed and values are lists of affected file paths:
- `Created`: Files created.
- `Modified`: Files updated via code blocks or diffs.
- `Renamed`: Files moved (formatted as `old -> new`).
- `Deleted`: Files moved to the trash directory.
- `Failed`: Files that could not be processed.
- `Message`: Status messages (e.g., "Nothing to do").

### `FormatResult`

A helper function to convert the result map from `Apply` into a human-readable, colorized string suitable for terminal output.

```go
func FormatResult(results map[string][]string) string
```

## Configuration

The `Config` struct controls how `itf` processes the input.

```go
type Config struct {
	OutputDiffFix bool     // Print corrected diff instead of applying
	Undo          bool     // Undo the last operation
	Redo          bool     // Redo the last undone operation
	Extensions    []string // Filter changes by file extension (e.g., ".go")
	Files         []string // Filter changes by specific file paths
}
```

## Example Usage

```go
package main

import (
	"fmt"
	"log"
	"github.com/sokinpui/itf"
)

func main() {
	markdown := "`hello.go` \n" +
		"```go\n" +
		"package main\n" +
		"func main() { println(\"hello\") }\n" +
		"```"

	config := itf.Config{
		Extensions: []string{".go"},
	}

	results, err := itf.Apply(markdown, config)
	if err != nil {
		log.Fatalf("Error applying changes: %v", err)
	}

	// Print summary using the built-in formatter
	fmt.Print(itf.FormatResult(results))

	// Or access results directly
	fmt.Printf("Modified files: %v\n", results["Modified"])
}
```
