package itf

type FileChange struct {
	Path     string
	Content  []string
	Source   string
	RawBlock string
}

type DiffBlock struct {
	FilePath   string
	RawContent string
}

type FileRename struct {
	OldPath string
	NewPath string
}

type Summary struct {
	Created  []string
	Modified []string
	Renamed  []string
	Deleted  []string
	Failed   []string
	Message  string
}
