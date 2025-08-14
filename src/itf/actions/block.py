# src/itf/actions/block.py
from typing import Dict, List, Set, Tuple

from ..parser import parse_file_blocks
from .base import ContentProcessingAction


class BlockAction(ContentProcessingAction):
    def _plan_changes(
        self, content: str
    ) -> Tuple[List[Tuple[str, List[str]]], Dict[str, str], Set[str]]:
        file_blocks_rel = list(parse_file_blocks(content))
        if not file_blocks_rel:
            return [], {}, set()

        file_blocks = [
            (self.path_resolver.resolve(fp), content) for fp, content in file_blocks_rel
        ]

        target_paths = [fp for fp, _ in file_blocks]
        file_actions, dirs_to_create = self._get_file_actions_and_dirs(target_paths)

        return file_blocks, file_actions, dirs_to_create
