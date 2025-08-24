# ./src/itf/patcher.py
import os
import re
import subprocess
import tempfile
from typing import Iterator, List, Optional, Tuple

from .diff_corrector import correct_diff
from .path_resolver import PathResolver
from .printer import print_error, print_info, print_success, print_warning

# Regex to find a complete markdown-style diff block.
DIFF_BLOCK_REGEX = re.compile(
    r"^[`]{3,}\s*diff\s*\n"  # Start of diff block
    # Content: everything until a new fence is found or EOF.
    # The negative lookahead `(?!^`{3,})` prevents matching across block boundaries.
    r"((?:(?!^`{3,})[\s\S])*)",
    re.MULTILINE,
)


# Regex to extract a file path from a '+++ b/...' line in a diff.
FILE_PATH_REGEX = re.compile(r"^\+\+\+ b/(?P<path>.*?)(\s|$)", re.MULTILINE)


def extract_target_paths(
    source_content: str, extensions: Optional[List[str]] = None
) -> Iterator[str]:
    """
    Parses content for diff blocks and yields the target file paths without
    applying any changes.
    """
    for match in DIFF_BLOCK_REGEX.finditer(source_content):
        patch_content = match.group(1)
        path_match = FILE_PATH_REGEX.search(patch_content)
        if path_match:
            file_path = path_match.group("path").strip()
            if extensions and os.path.splitext(file_path)[1] not in extensions:
                continue
            yield file_path


def generate_patched_contents(
    source_content: str,
    path_resolver: PathResolver,
    extensions: Optional[List[str]] = None,
) -> Iterator[Tuple[str, List[str]]]:
    """
    Finds diff blocks, corrects them, and yields the patched content.

    For each diff, it reads the original file, uses the diff corrector to
    generate a valid patch, applies it to a temporary copy, and yields the
    final content lines.

    Yields:
        A tuple of (file_path, list_of_patched_content_lines).
    """
    diff_matches = list(DIFF_BLOCK_REGEX.finditer(source_content))
    if not diff_matches:
        print_warning("No '```diff' blocks found in the source content.")
        return

    print_info(f"Found {len(diff_matches)} diff block(s) to process.")

    for match in diff_matches:
        patch_content_raw = match.group(1).strip()
        if not patch_content_raw:
            continue

        path_match = FILE_PATH_REGEX.search(patch_content_raw)
        if not path_match:
            print_warning(
                "  -> Found a diff block but could not extract a file path. Skipping."
            )
            print_warning(f"     Block starts with: '{patch_content_raw.splitlines()}'")
            continue

        file_path = path_match.group("path").strip()
        if extensions and os.path.splitext(file_path)[1] not in extensions:
            continue

        resolved_source_path = path_resolver.resolve_existing(file_path)

        source_lines = []
        source_for_patch = resolved_source_path
        dummy_path = None
        if source_for_patch:
            try:
                with open(source_for_patch, "r", encoding="utf-8") as f:
                    source_lines = [line.rstrip("\n") for line in f.readlines()]
            except IOError as e:
                print_error(f"  -> Could not read source file {file_path}: {e}")
                continue
        else:
            dummy_fd, dummy_path = tempfile.mkstemp()
            os.close(dummy_fd)
            source_for_patch = dummy_path

        print_info(f"  -> Correcting diff for: {file_path}")
        corrected_patch_content = correct_diff(
            source_lines, patch_content_raw, file_path
        )

        if not corrected_patch_content:
            print_warning(
                f"  -> Diff correction failed or produced no output for {file_path}. Skipping."
            )
            continue

        output_fd, output_path = tempfile.mkstemp()
        os.close(output_fd)

        try:
            command = ["patch", "-p1", "-o", output_path, source_for_patch]
            result = subprocess.run(
                command,
                input=corrected_patch_content,
                text=True,
                capture_output=True,
                cwd=os.getcwd(),
            )

            if result.returncode != 0:
                print_error(f"  -> Failed to generate patch for: {file_path}")
                error_details = result.stderr.strip()
                print_error(f"     `patch` command failed:\n{error_details}")
                continue

            print_success(f"  -> Successfully generated patch for: {file_path}")
            if result.stdout:
                print_info(f"     {result.stdout.strip()}")

            with open(output_path, "r", encoding="utf-8") as f:
                patched_lines = [line.rstrip("\n") for line in f.readlines()]

            # Yield the final absolute path for the file.
            yield path_resolver.resolve(file_path), patched_lines

        finally:
            if dummy_path:
                os.remove(dummy_path)
            os.remove(output_path)
