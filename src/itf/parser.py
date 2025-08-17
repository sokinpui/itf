# src/itf/parser.py
import os
import re
from typing import Iterator, List, Tuple


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


# Regex to find an optional file path hint followed by a markdown code block.
BLOCK_WITH_OPTIONAL_HINT_REGEX = re.compile(
    r"(?:^.*?`(?P<path_hint>[^`\n]+)`.*\n)?"  # Optional: `path/hint` on a line
    r"^[`]{3,}(?P<lang>[a-z]*)\s*\n"  # Start of code block
    # Content: everything until a new fence is found or EOF.
    # The negative lookahead `(?!^`{3,})` prevents matching across block boundaries.
    r"(?P<content>((?:(?!^`{3,})[\s\S])*))",
    re.MULTILINE,
)

# Regex to extract a file path from a comment on the first line of content.
PATH_EXTRACT_REGEX = re.compile(r"^(?:#|//|/\*)\s*(?P<path>.*?)\s*(?:\*/)?$")


def parse_file_blocks(source_content: str) -> Iterator[Tuple[str, List[str]]]:
    """
    Parses content for file blocks and yields file paths and their content.

    It handles two ways of specifying a file path:
    1. An explicit path in a comment on the first line of the code block (preferred).
    2. A path on its own line in backticks just before the code block.

    If a path is specified in both places, the one inside the block is used.

    Args:
        source_content: The string content to parse.

    Yields:
        A tuple containing the extracted file path and a list of content lines.
    """
    for match in BLOCK_WITH_OPTIONAL_HINT_REGEX.finditer(source_content):
        # 'diff' blocks are processed by the patcher, not by this function.
        # This ensures that file block parsing ignores diffs.
        if match.group("lang") == "diff":
            continue

        path_hint = match.group("path_hint")
        content = match.group("content")

        # rstrip to prevent a trailing newline in the block from creating
        # an extra empty line at the end. Then split into lines.
        content_lines = content.rstrip("\n").split("\n")

        # If the block was empty or just whitespace, treat as empty list.
        if content_lines == [""]:
            content_lines = []

        first_line = content_lines[0].strip() if content_lines else ""

        file_path = None
        lines_to_write = content_lines

        # Case 1: Path is embedded as a comment in the first line of the block.
        path_match = PATH_EXTRACT_REGEX.search(first_line)
        if path_match:
            extracted_path = path_match.group("path").strip()
            if extracted_path:
                file_path = extracted_path
                # Content is used as-is, as it already contains the header.
                lines_to_write = content_lines

        # Case 2: No embedded path, but a path hint was found before the block.
        elif path_hint:
            hinted_path = path_hint.strip()
            if hinted_path:
                file_path = hinted_path
                # Prepend the file path as a commented header.
                prefix, suffix = _get_comment_format(file_path)
                header = f"{prefix} {file_path} {suffix}".strip()
                lines_to_write = [header] + content_lines

        if not file_path:
            continue

        yield file_path, lines_to_write
