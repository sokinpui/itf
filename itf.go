package itf

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"
)

type Config struct {
	Buffer        bool
	OutputTool    bool
	OutputDiffFix bool
	Undo          bool
	Redo          bool
	Extensions    []string
	Files         []string
}

type ProgressUpdate func(current, total int)

type App struct {
	cfg              *Config
	stateManager     *StateManager
	pathResolver     *PathResolver
	sourceProvider   *SourceProvider
	progressCallback ProgressUpdate
}

type DetailedError struct {
	Err   error
	Stack []byte
}

func (e *DetailedError) Error() string { return e.Err.Error() }

func NewApp(cfg *Config) (*App, error) {
	sm, err := NewStateManager()
	if err != nil {
		return nil, err
	}
	return &App{
		cfg:            cfg,
		stateManager:   sm,
		pathResolver:   NewPathResolver(),
		sourceProvider: NewSourceProvider(),
	}, nil
}

func (a *App) SetProgressCallback(cb ProgressUpdate) { a.progressCallback = cb }

func (a *App) Execute() (summary Summary, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = &DetailedError{Err: fmt.Errorf("panic: %v", r), Stack: debug.Stack()}
		}
	}()

	switch {
	case a.cfg.Undo:
		return a.undoLastOperation()
	case a.cfg.Redo:
		return a.redoLastOperation()
	case a.cfg.OutputTool:
		return a.printTools()
	case a.cfg.OutputDiffFix:
		return a.fixAndPrintDiffs()
	default:
		return a.processContent()
	}
}

func (a *App) processContent() (Summary, error) {
	c, err := a.sourceProvider.GetContent()
	if err != nil || c == "" {
		return Summary{Message: "Empty source"}, err
	}
	return a.processAndApply(c)
}

func (a *App) processAndApply(content string) (Summary, error) {
	plan, err := CreatePlan(content, a.pathResolver, a.cfg.Extensions, a.cfg.Files)
	if err != nil {
		return Summary{}, err
	}
	if len(plan.Changes) == 0 && len(plan.Deletes) == 0 && len(plan.Renames) == 0 {
		return Summary{Message: "Nothing to do"}, nil
	}

	CreateDirs(plan.DirsToCreate)
	return a.applyChanges(plan)
}

func (a *App) applyChanges(plan *ExecutionPlan) (Summary, error) {
	m, err := NewNvimManager()
	if err != nil {
		return Summary{}, err
	}
	defer m.Close()

	oldHashes := make(map[string]string)
	for _, c := range plan.Changes {
		h, _ := GetFileSHA256(c.Path)
		oldHashes[c.Path] = h
		if h != "" {
			content, _ := os.ReadFile(c.Path)
			_ = WriteBlob(a.stateManager.StateDir, h, content)
		}
	}

	var deleted, failedDeletes []string
	trash := filepath.Join(a.stateManager.StateDir, TrashDir)
	for _, p := range plan.Deletes {
		h, _ := GetFileSHA256(p)
		oldHashes[p] = h
		if h != "" {
			content, _ := os.ReadFile(p)
			_ = WriteBlob(a.stateManager.StateDir, h, content)
		}
		if TrashFile(p, trash, ".") == nil {
			deleted = append(deleted, p)
		} else {
			failedDeletes = append(failedDeletes, p)
		}
	}

	var renamedSuccess []string
	renamed := make(map[string]string)
	var failedRenames []string
	for _, r := range plan.Renames {
		h, _ := GetFileSHA256(r.OldPath)
		oldHashes[r.OldPath] = h
		if h != "" {
			content, _ := os.ReadFile(r.OldPath)
			_ = WriteBlob(a.stateManager.StateDir, h, content)
		}
		if os.Rename(r.OldPath, r.NewPath) == nil {
			renamed[r.OldPath] = r.NewPath
			renamedSuccess = append(renamedSuccess, r.OldPath)
		} else {
			failedRenames = append(failedRenames, r.OldPath)
		}
	}

	updated, failedNvim := m.ApplyChanges(plan.Changes, func(c int) {
		a.reportProgress(c, len(plan.Changes))
	})

	if !a.cfg.Buffer && len(updated)+len(deleted)+len(renamedSuccess) > 0 {
		m.SaveAllBuffers()
		historyPaths := append(updated, deleted...)
		historyPaths = append(historyPaths, renamedSuccess...)
		ops := a.stateManager.CreateOperations(historyPaths, plan.FileActions, plan.Renames, oldHashes)
		a.stateManager.Write(ops)
	}

	var created, modified []string
	for _, p := range updated {
		if plan.FileActions[p] == "create" {
			created = append(created, p)
		} else {
			modified = append(modified, p)
		}
	}

	return a.createSummary(created, modified, deleted, renamed, failedNvim, failedDeletes, failedRenames)
}

func (a *App) reportProgress(current, total int) {
	if a.progressCallback != nil {
		a.progressCallback(current, total)
	}
}

func (a *App) createSummary(created, modified, deleted []string, renamed map[string]string, failedNvim, failedDeletes, failedRenames []string) (Summary, error) {
	var renamedPaths []string
	for oldPath, newPath := range renamed {
		renamedPaths = append(renamedPaths, fmt.Sprintf("%s -> %s", oldPath, newPath))
	}

	s := Summary{
		Created:  created,
		Modified: modified,
		Deleted:  deleted,
		Renamed:  renamedPaths,
		Failed:   append(failedNvim, append(failedDeletes, failedRenames...)...),
	}
	a.relativizeSummaryPaths(&s)
	return s, nil
}

func (a *App) fixAndPrintDiffs() (Summary, error) {
	c, _ := a.sourceProvider.GetContent()
	diffs := ExtractDiffBlocks(c, a.pathResolver, a.cfg.Files)
	for _, d := range diffs {
		if res, err := CorrectDiff(d, a.pathResolver, a.cfg.Extensions); err == nil {
			fmt.Print(res)
		}
	}
	return Summary{}, nil
}

func (a *App) printTools() (Summary, error) {
	c, _ := a.sourceProvider.GetContent()
	tools, _ := ExtractToolBlocks(c)
	for _, t := range tools {
		fmt.Println(t.Content)
	}
	return Summary{}, nil
}

func (a *App) undoLastOperation() (Summary, error) {
	ops := a.stateManager.GetOperationsToUndo()
	if len(ops) == 0 {
		return Summary{Message: "No undo"}, nil
	}
	m, _ := NewNvimManager()
	defer m.Close()
	s := m.UndoFiles(ops, a.stateManager.StateDir, nil)
	s.Message = "Undone"
	a.relativizeSummaryPaths(&s)
	return s, nil
}

func (a *App) redoLastOperation() (Summary, error) {
	ops := a.stateManager.GetOperationsToRedo()
	if len(ops) == 0 {
		return Summary{Message: "No redo"}, nil
	}
	m, _ := NewNvimManager()
	defer m.Close()
	s := m.RedoFiles(ops, a.stateManager.StateDir, nil)
	s.Message = "Redone"
	a.relativizeSummaryPaths(&s)
	return s, nil
}

func (a *App) relativizeSummaryPaths(s *Summary) {
	wd, _ := os.Getwd()
	relPath := func(p string) string {
		if r, err := filepath.Rel(wd, p); err == nil {
			return r
		}
		return p
	}

	relList := func(paths []string) []string {
		var res []string
		for _, p := range paths {
			if strings.Contains(p, " -> ") {
				parts := strings.SplitN(p, " -> ", 2)
				res = append(res, fmt.Sprintf("%s -> %s", relPath(parts[0]), relPath(parts[1])))
			} else {
				res = append(res, relPath(p))
			}
		}
		return res
	}
	s.Created = relList(s.Created)
	s.Modified = relList(s.Modified)
	s.Deleted = relList(s.Deleted)
	s.Renamed = relList(s.Renamed)
	s.Failed = relList(s.Failed)
}
