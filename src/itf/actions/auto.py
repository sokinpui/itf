# src/itf/actions/auto.py
import os
import shutil
import sys
from typing import Dict, List, Set, Tuple

from ..parser import parse_file_blocks
from ..patcher import extract_target_paths, generate_patched_contents
from ..printer import print_header, print_info, print_path, print_warning
from .base import ContentProcessingAction


class AutoAction(ContentProcessingAction):
    def _plan_changes(
        self, content: str
    ) -> Tuple[List[Tuple[str, List[str]]], Dict[str, str], Set[str]]:
        print_header("--- Auto-detecting and applying changes ---")
        if not shutil.which("patch"):
            print_error("`patch` command not found. It is required for --auto mode.")
            sys.exit(1)

        diff_paths = list(extract_target_paths(content))
        block_blocks = list(parse_file_blocks(content))
        block_paths = [fp for fp, _ in block_blocks]

        all_paths = diff_paths + block_paths
        if not all_paths:
            return [], {}, set()

        file_actions, dirs_to_create = self._get_file_actions_and_dirs(all_paths)

        print_info("\nGenerating patched content from diffs...")
        diff_blocks = list(generate_patched_contents(content))

        self._warn_on_overwrite(diff_blocks, block_blocks)

        final_blocks_map = {os.path.abspath(fp): (fp, c) for fp, c in diff_blocks}
        final_blocks_map.update(
            {os.path.abspath(fp): (fp, c) for fp, c in block_blocks}
        )

        return list(final_blocks_map.values()), file_actions, dirs_to_create

    @staticmethod
    def _warn_on_overwrite(
        diff_blocks: List[Tuple[str, List[str]]],
        block_blocks: List[Tuple[str, List[str]]],
    ) -> None:
        paths_from_diffs = {os.path.abspath(fp) for fp, _ in diff_blocks}
        paths_from_blocks = {os.path.abspath(fp) for fp, _ in block_blocks}
        intersection = paths_from_diffs.intersection(paths_from_blocks)

        if intersection:
            print_warning(
                "\nWarning: The following files are targeted by both a diff and a file block:"
            )
            for p in sorted(list(intersection)):
                print_path(f"- {p}")
            print_warning("The file block content will overwrite the diff patch result.")
