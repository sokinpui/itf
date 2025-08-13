# src/itf/actions/diff_fix.py
import os
import sys

from ..diff_corrector import correct_diff
from ..patcher import DIFF_BLOCK_REGEX, FILE_PATH_REGEX
from ..source import SourceProvider
from .base import Action


class DiffFixAction(Action):
    def execute(self) -> None:
        source_provider = SourceProvider(self.args)
        content = source_provider.get_content()
        if not content:
            return

        corrected_diffs = []
        for match in DIFF_BLOCK_REGEX.finditer(content):
            patch_content_raw = match.group(1).strip()
            if not patch_content_raw:
                continue

            path_match = FILE_PATH_REGEX.search(patch_content_raw)
            if not path_match:
                continue

            file_path = path_match.group("path").strip()
            abs_file_path = os.path.abspath(file_path)

            source_lines = []
            if os.path.exists(abs_file_path):
                try:
                    with open(abs_file_path, "r", encoding="utf-8") as f:
                        source_lines = [line.rstrip("\n") for line in f.readlines()]
                except IOError:
                    pass

            corrected_patch = correct_diff(source_lines, patch_content_raw, file_path)
            if corrected_patch:
                corrected_diffs.append(corrected_patch)

        if corrected_diffs:
            print("".join(corrected_diffs), end="", file=sys.stdout)
