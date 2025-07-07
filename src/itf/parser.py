# src/itf/parser.py
import re
from typing import Iterator, Tuple

# Regex to find a complete markdown-style code block.
FILE_BLOCK_REGEX = re.compile(
    r"```[a-z]*\n(?P<content_with_header>(?:#|//|/\*)\s*.*?\n.*?)\n```", re.DOTALL
)

# Regex to extract a file path from the first line of a block's content.
# Supports C-style (#), C++-style (//), and block comments (/* ... */).
PATH_EXTRACT_REGEX = re.compile(r"^(?:#|//|/\*)\s*(?P<path>.*?)\s*(?:\*/)?$")


def parse_file_blocks(source_content: str) -> Iterator[Tuple[str, list[str]]]:
    """
    Parses content for file blocks and yields file paths and their content.

    A file block is a markdown code block where the first line is a comment
    containing the target file path.

    Args:
        source_content: The string content to parse.

    Yields:
        A tuple containing the extracted file path and a list of content lines.
    """
    for match in FILE_BLOCK_REGEX.finditer(source_content):
        content_with_header = match.group("content_with_header")

        # The header is the first line, the rest is the actual content.
        header, *content_lines = content_with_header.split("\n")

        path_match = PATH_EXTRACT_REGEX.search(header.strip())
        if not path_match:
            continue

        file_path = path_match.group("path").strip()

        # The content to be written includes the header line (with the file path).
        lines_to_write = [header] + content_lines

        yield file_path, lines_to_write
