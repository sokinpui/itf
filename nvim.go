package itf

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/neovim/go-client/nvim"
)

const undoDir = "~/.local/state/nvim/undo/"

type NvimManager struct {
	v             *nvim.Nvim
	isSelfStarted bool
	cmd           *exec.Cmd
	socketPath    string
}

func NewNvimManager() (*NvimManager, error) {
	if addr := os.Getenv("NVIM_LISTEN_ADDRESS"); addr != "" {
		v, err := nvim.Dial(addr)
		if err == nil {
			return &NvimManager{v: v}, nil
		}
	}

	tmpDir, err := os.MkdirTemp("", "itf-nvim-")
	if err != nil {
		return nil, err
	}
	socketPath := filepath.Join(tmpDir, "nvim.sock")

	cmd := exec.Command("nvim", "--headless", "--clean", "--listen", socketPath)
	if err := cmd.Start(); err != nil {
		return nil, err
	}

	for i := 0; i < 20; i++ {
		if _, err := os.Stat(socketPath); err == nil {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	v, err := nvim.Dial(socketPath)
	if err != nil {
		cmd.Process.Kill()
		return nil, err
	}

	m := &NvimManager{v: v, isSelfStarted: true, cmd: cmd, socketPath: socketPath}
	m.configureTempInstance()
	return m, nil
}

func (m *NvimManager) configureTempInstance() {
	home, _ := os.UserHomeDir()
	expandedUndoDir := strings.Replace(undoDir, "~", home, 1)
	os.MkdirAll(expandedUndoDir, 0755)

	b := m.v.NewBatch()
	b.Command("set undofile")
	b.Command(fmt.Sprintf("set undodir=%s", expandedUndoDir))
	b.Command("set noswapfile")
	b.Execute()
}

func (m *NvimManager) Close() {
	if m.v != nil {
		m.v.Close()
	}
	if m.isSelfStarted && m.cmd != nil && m.cmd.Process != nil {
		m.cmd.Process.Kill()
		m.cmd.Wait()
		os.RemoveAll(filepath.Dir(m.socketPath))
	}
}

func (m *NvimManager) ApplyChanges(changes []FileChange, progressCb func(int)) (updated, failed []string) {
	for i, change := range changes {
		if m.updateBuffer(change.Path, change.Content) {
			updated = append(updated, change.Path)
		} else {
			failed = append(failed, change.Path)
		}
		if progressCb != nil {
			progressCb(i + 1)
		}
	}
	return updated, failed
}

func (m *NvimManager) updateBuffer(filePath string, content []string) bool {
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		return false
	}

	byteContent := make([][]byte, len(content))
	for i, s := range content {
		byteContent[i] = []byte(s)
	}

	b := m.v.NewBatch()
	b.Command(fmt.Sprintf("edit %s", absPath))
	b.SetBufferLines(0, 0, -1, true, byteContent)

	return b.Execute() == nil
}

func (m *NvimManager) SaveAllBuffers() {
	m.v.Command("wa!")
}

func (m *NvimManager) UndoFiles(ops []Operation, stateDir string, progressCb func(int)) (undone, failed []string) {
	for i, op := range ops {
		if m.undoFile(op, stateDir) {
			undone = append(undone, op.Path)
		} else {
			failed = append(failed, op.Path)
		}
		if progressCb != nil {
			progressCb(i + 1)
		}
	}
	return undone, failed
}

func (m *NvimManager) undoFile(op Operation, stateDir string) bool {
	if op.Action == "delete" {
		return RestoreFileFromTrash(op.Path, filepath.Join(stateDir, TrashDir), ".") == nil
	}

	if op.Action == "rename" {
		return os.Rename(op.NewPath, op.Path) == nil
	}

	currentHash, err := GetFileSHA256(op.Path)
	if err != nil {
		return op.Action == "create" && os.IsNotExist(err)
	}

	if currentHash != op.ContentHash {
		return false
	}

	if op.Action == "create" {
		return os.Remove(op.Path) == nil
	}

	absPath, _ := filepath.Abs(op.Path)
	b := m.v.NewBatch()
	b.Command(fmt.Sprintf("edit! %s", absPath))
	b.Command("undo")
	b.Command("write")
	return b.Execute() == nil
}

func (m *NvimManager) RedoFiles(ops []Operation, stateDir string, progressCb func(int)) (redone, failed []string) {
	for i, op := range ops {
		success := false
		switch op.Action {
		case "delete":
			success = TrashFile(op.Path, filepath.Join(stateDir, TrashDir), ".") == nil
		case "create", "modify":
			success = m.redoBufferOp(op.Path)
		case "rename":
			success = os.Rename(op.Path, op.NewPath) == nil
		}

		if success {
			redone = append(redone, op.Path)
		} else {
			failed = append(failed, op.Path)
		}
		if progressCb != nil {
			progressCb(i + 1)
		}
	}
	return redone, failed
}

func (m *NvimManager) redoBufferOp(filePath string) bool {
	absPath, _ := filepath.Abs(filePath)
	b := m.v.NewBatch()
	b.Command(fmt.Sprintf("edit! %s", absPath))
	b.Command("redo")
	b.Command("write")
	return b.Execute() == nil
}
