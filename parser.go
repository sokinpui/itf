package itf

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

type ExecutionPlan struct {
	Changes      []FileChange
	Deletes      []string
	Renames      []FileRename
	FileActions  map[string]string
	DirsToCreate map[string]struct{}
	Failed       []string
}

var pathInHintRegex = regexp.MustCompile("^`([^`\n]+)`")

func CreatePlan(content string, resolver *PathResolver, extensions []string, files []string) (*ExecutionPlan, error) {
	allowedFiles := make(map[string]struct{})
	for _, f := range files {
		allowedFiles[resolver.Resolve(f)] = struct{}{}
	}

	allBlocks, err := ExtractCodeBlocks([]byte(content))
	if err != nil {
		return nil, err
	}

	isDiffOnly := len(extensions) == 1 && extensions[0] == ".diff"
	var fileBlocks []FileChange
	if !isDiffOnly {
		fileBlocks = parseFileBlocks(allBlocks, resolver, extensions, allowedFiles)
	}

	renames := parseRenameBlocks(allBlocks, resolver, allowedFiles)
	renameDestToSource := make(map[string]string)
	renameDestSet := make(map[string]struct{})
	for _, r := range renames {
		renameDestToSource[r.NewPath] = r.OldPath
		renameDestSet[r.NewPath] = struct{}{}
	}

	diffBlocks := extractDiffBlocksFromParsed(allBlocks, resolver, allowedFiles)
	deletePaths := parseDeletePaths(allBlocks, resolver, allowedFiles)
	patchedChanges, failedPatches, err := GeneratePatchedContents(diffBlocks, resolver, extensions, renameDestToSource)
	if err != nil {
		return nil, err
	}

	finalChanges := make(map[string]FileChange)
	for _, c := range patchedChanges {
		finalChanges[c.Path] = c
	}
	for _, b := range fileBlocks {
		finalChanges[b.Path] = b
	}

	planChanges := make([]FileChange, 0, len(finalChanges))
	targetPaths := make([]string, 0, len(finalChanges))
	for _, c := range finalChanges {
		planChanges = append(planChanges, c)
		targetPaths = append(targetPaths, c.Path)
	}

	actions, dirs := GetFileActionsAndDirs(targetPaths, renameDestSet)
	for _, p := range deletePaths {
		actions[p] = "delete"
	}
	for _, r := range renames {
		actions[r.OldPath] = "rename"
		dir := filepath.Dir(r.NewPath)
		if dir != "." && dir != "/" {
			if _, err := os.Stat(dir); os.IsNotExist(err) {
				dirs[dir] = struct{}{}
			}
		}
	}

	return &ExecutionPlan{
		Changes:      planChanges,
		Deletes:      deletePaths,
		Renames:      renames,
		FileActions:  actions,
		DirsToCreate: dirs,
		Failed:       failedPatches,
	}, nil
}

func parseFileBlocks(blocks []CodeBlock, resolver *PathResolver, extensions []string, allowed map[string]struct{}) []FileChange {
	var result []FileChange
	for _, b := range blocks {
		if b.Lang == "diff" || b.Lang == "delete" || b.Lang == "rename" {
			continue
		}
		path := ExtractPathFromHint(b.Hint)
		if path == "" {
			continue
		}
		abs := resolver.Resolve(path)
		if len(allowed) > 0 {
			if _, ok := allowed[abs]; !ok {
				continue
			}
		}
		if !HasAllowedExtension(path, extensions) {
			continue
		}

		trimmed := strings.TrimRight(b.Content, "\n")
		lines := strings.Split(trimmed, "\n")
		if len(lines) == 1 && lines[0] == "" {
			lines = []string{}
		}

		result = append(result, FileChange{
			Path:     abs,
			Content:  lines,
			Source:   "codeblock",
			RawBlock: fmt.Sprintf("```%s\n%s\n```", b.Lang, trimmed),
		})
	}
	return result
}

func ExtractDiffBlocks(content string, resolver *PathResolver, files []string) []DiffBlock {
	blocks, _ := ExtractCodeBlocks([]byte(content))
	allowed := make(map[string]struct{})
	for _, f := range files {
		allowed[resolver.Resolve(f)] = struct{}{}
	}
	return extractDiffBlocksFromParsed(blocks, resolver, allowed)
}

func extractDiffBlocksFromParsed(blocks []CodeBlock, resolver *PathResolver, allowed map[string]struct{}) []DiffBlock {
	var diffs []DiffBlock
	for _, b := range blocks {
		if b.Lang != "diff" {
			continue
		}
		raw := strings.Trim(b.Content, "\n")
		path := ExtractPathFromDiff(raw)
		if path == "" {
			continue
		}
		if len(allowed) > 0 {
			if _, ok := allowed[resolver.Resolve(path)]; !ok {
				continue
			}
		}
		diffs = append(diffs, DiffBlock{FilePath: path, RawContent: raw})
	}
	return diffs
}

func ExtractPathFromHint(hint string) string {
	if match := pathInHintRegex.FindStringSubmatch(strings.TrimSpace(hint)); len(match) > 1 {
		path := strings.TrimSpace(match[1])
		if !strings.Contains(path, " ") {
			return path
		}
	}
	return ""
}

func HasAllowedExtension(path string, extensions []string) bool {
	if len(extensions) == 0 {
		return true
	}
	ext := filepath.Ext(path)
	for _, e := range extensions {
		if ext == e {
			return true
		}
	}
	return false
}

func parseDeletePaths(blocks []CodeBlock, resolver *PathResolver, allowed map[string]struct{}) []string {
	var paths []string
	for _, b := range blocks {
		if b.Lang != "delete" {
			continue
		}
		for _, line := range strings.Split(b.Content, "\n") {
			trimmed := strings.TrimSpace(line)
			if trimmed == "" {
				continue
			}
			abs := resolver.Resolve(trimmed)
			if len(allowed) > 0 {
				if _, ok := allowed[abs]; !ok {
					continue
				}
			}
			paths = append(paths, abs)
		}
	}
	return paths
}

func parseRenameBlocks(blocks []CodeBlock, resolver *PathResolver, allowed map[string]struct{}) []FileRename {
	var renames []FileRename
	for _, b := range blocks {
		if b.Lang != "rename" {
			continue
		}
		for _, line := range strings.Split(b.Content, "\n") {
			parts := strings.Fields(strings.TrimSpace(line))
			if len(parts) != 2 {
				continue
			}
			oldAbs, newAbs := resolver.Resolve(parts[0]), resolver.Resolve(parts[1])
			if len(allowed) > 0 {
				_, ok1 := allowed[oldAbs]
				_, ok2 := allowed[newAbs]
				if !ok1 && !ok2 {
					continue
				}
			}
			renames = append(renames, FileRename{OldPath: oldAbs, NewPath: newAbs})
		}
	}
	return renames
}
