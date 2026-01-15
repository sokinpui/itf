package itf

import (
	"regexp"
	"strings"
)

var hunkHeaderPattern = regexp.MustCompile(`^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@`)

func ReverseDiff(patch string) string {
	lines := strings.Split(patch, "\n")
	var reversed []string

	for i := 0; i < len(lines); i++ {
		if isHeaderPair(lines, i) {
			reversed = append(reversed, "--- "+lines[i+1][4:])
			reversed = append(reversed, "+++ "+lines[i][4:])
			i++
			continue
		}

		reversed = append(reversed, reverseSingleLine(lines[i]))
	}

	return strings.Join(reversed, "\n")
}

func isHeaderPair(lines []string, index int) bool {
	return index+1 < len(lines) &&
		strings.HasPrefix(lines[index], "--- ") &&
		strings.HasPrefix(lines[index+1], "+++ ")
}

func reverseSingleLine(line string) string {
	if strings.HasPrefix(line, "--- ") {
		return "+++ " + line[4:]
	}

	if strings.HasPrefix(line, "+++ ") {
		return "--- " + line[4:]
	}

	if strings.HasPrefix(line, "@@ ") {
		return swapHunkRanges(line)
	}

	if strings.HasPrefix(line, "+") {
		return "-" + line[1:]
	}

	if strings.HasPrefix(line, "-") {
		return "+" + line[1:]
	}

	return line
}

func swapHunkRanges(line string) string {
	matches := hunkHeaderPattern.FindStringSubmatch(line)
	if len(matches) < 3 {
		return line
	}

	return "@@ -" + matches[2] + " +" + matches[1] + " @@"
}
