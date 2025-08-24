# src/itf/parser.py
import os
import re
from typing import Iterator, List, Optional, Tuple


def _get_comment_format(file_path: str) -> Tuple[str, str]:
    """
    Determines the comment syntax (prefix, suffix) for a given file path.
    Returns a tuple, e.g., ("#", "") for Python or ("/*", "*/") for CSS.
    """
    filename = os.path.basename(file_path)
    _, extension = os.path.splitext(filename)
    ext = extension.lower()

    # (prefix, suffix)
    syntax_map = {
        ".py": ("#", ""),
        ".rb": ("#", ""),
        ".sh": ("#", ""),
        ".yaml": ("#", ""),
        ".yml": ("#", ""),
        ".dockerfile": ("#", ""),
        ".js": ("//", ""),
        ".ts": ("//", ""),
        ".java": ("//", ""),
        ".c": ("//", ""),
        ".cpp": ("//", ""),
        ".h": ("//", ""),
        ".hpp": ("//", ""),
        ".cs": ("//", ""),
        ".go": ("//", ""),
        ".rs": ("//", ""),
        ".dart": ("//", ""),
        ".kt": ("//", ""),
        ".kts": ("//", ""),
        ".swift": ("//", ""),
        ".scala": ("//", ""),
        ".scss": ("//", ""),
        ".less": ("//", ""),
        ".sql": ("--", ""),
        ".lua": ("--", ""),
        ".html": ("<!--", "-->"),
        ".xml": ("<!--", "-->"),
        ".css": ("/*", "*/"),
    }

    # Handle files with special names or no extension
    if "makefile" in filename.lower():
        return "#", ""

    # Default to a common C-style syntax if not found
    return syntax_map.get(ext, ("//", ""))


# Regex to find a markdown code block and the line preceding it, which may
# contain a path hint. It supports various markdown styles for the hint and
# allows for an optional empty line between the hint and the code block.
BLOCK_WITH_OPTIONAL_HINT_REGEX = re.compile(
    # Optional: A "hint line" that isn't a code fence, possibly followed by a blank line.
    r"(?:^(?![`]{3,})(?P<hint_line>[^\n]*)\n(?:\s*\n)?)?"
    r"^[`]{3,}(?P<lang>[a-z]*)\s*\n"  # Start of code block
    # Content: everything until the closing code fence (non-greedy).
    r"(?P<content>[\s\S]*?)"
    r"^\s*[`]{3,}\s*$",  # Closing fence on its own line
    re.MULTILINE,
)


def _extract_path_from_hint(hint_line: Optional[str]) -> Optional[str]:
    """
    Extracts a file path from a hint line by stripping common markdown syntax.

    It prioritizes paths in backticks, then falls back to cleaning the line
    of headers and bold markers to find a single path-like token.
    Example: `**`path/to/file.py`**` -> `path/to/file.py`
    """
    if not hint_line:
        return None

    hint = hint_line.strip()

    match = re.search(r"`([^`\n]+)`", hint)
    if match:
        path_candidate = match.group(1).strip()
        if " " not in path_candidate and path_candidate:
            return path_candidate

    cleaned_hint = re.sub(r"^#+\s*", "", hint).strip()
    if cleaned_hint.startswith("**") and cleaned_hint.endswith("**") and len(cleaned_hint) > 4:
        cleaned_hint = cleaned_hint[2:-2]
    elif cleaned_hint.startswith("*") and cleaned_hint.endswith("*") and len(cleaned_hint) > 2:
        cleaned_hint = cleaned_hint[1:-1]

    cleaned_hint = cleaned_hint.strip()
    if " " not in cleaned_hint and cleaned_hint:
        return cleaned_hint

    return None


def parse_file_blocks(
    source_content: str, extensions: Optional[List[str]] = None
) -> Iterator[Tuple[str, List[str]]]:
    """
    Parses content for file blocks and yields file paths and their content.

    A valid file block is defined as a path hint on its own line, immediately
    followed by a markdown code block. Code blocks without a preceding path
    hint are ignored.

    Args:
        source_content: The string content to parse.
        extensions: An optional list of file extensions to filter by (e.g., ['.py', '.js']).

    Yields:
        A tuple containing the extracted file path and a list of content lines.
    """
    for match in BLOCK_WITH_OPTIONAL_HINT_REGEX.finditer(source_content):
        # 'diff' blocks are processed by the patcher, not by this function.
        # This ensures that file block parsing ignores diffs.
        if match.group("lang") == "diff":
            continue

        hint_line = match.group("hint_line")
        file_path = _extract_path_from_hint(hint_line)

        # A file block is only valid if it has a path hint.
        if not file_path:
            continue

        if extensions and os.path.splitext(file_path)[1] not in extensions:
            continue

        content = match.group("content")
        # rstrip to prevent a trailing newline in the block from creating
        # an extra empty line at the end. Then split into lines.
        content_lines = content.rstrip("\n").split("\n")

        # If the block was empty or just whitespace, treat as empty list.
        if content_lines == [""]:
            content_lines = []

        yield file_path, content_lines
