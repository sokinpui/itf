# src/itf/actions/diff.py
import shutil
import sys
from typing import Dict, List, Set, Tuple

from ..patcher import extract_target_paths, generate_patched_contents
from ..printer import print_error, print_header
from .base import ContentProcessingAction


class DiffAction(ContentProcessingAction):
    def _plan_changes(
        self, content: str
    ) -> Tuple[List[Tuple[str, List[str]]], Dict[str, str], Set[str]]:
        print_header("--- Parsing content as diffs and generating changes ---")
        if not shutil.which("patch"):
            print_error(
                "`patch` command not found. Please install it to use the --diff feature."
            )
            sys.exit(1)

        target_paths = list(extract_target_paths(content))
        if not target_paths:
            return [], {}, set()

        file_actions, dirs_to_create = self._get_file_actions_and_dirs(target_paths)
        file_blocks = list(generate_patched_contents(content))

        return file_blocks, file_actions, dirs_to_create
