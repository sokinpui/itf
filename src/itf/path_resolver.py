# src/itf/path_resolver.py
import os
from typing import List, Optional

from .printer import print_info


class PathResolver:
    def __init__(self, lookup_dirs: Optional[List[str]], find_root: bool):
        if lookup_dirs:
            self.lookup_dirs = [os.path.abspath(d) for d in lookup_dirs]
        elif find_root:
            project_root = self._find_project_root()
            if project_root:
                print_info(f"-> Project root found at: {project_root}")
                self.lookup_dirs = [project_root]
            else:
                self.lookup_dirs = [os.getcwd()]
        else:
            self.lookup_dirs = [os.getcwd()]

    @staticmethod
    def _find_project_root() -> Optional[str]:
        """
        Traverses up from the current directory to find a directory containing '.git'.
        """
        current_dir = os.getcwd()
        while True:
            if os.path.isdir(os.path.join(current_dir, ".git")):
                return current_dir

            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:  # Reached the filesystem root
                return None

            current_dir = parent_dir

    def resolve(self, relative_path: str) -> str:
        """
        Resolves a relative path to an absolute path.

        It searches for an existing file in the lookup directories. If not
        found, it assumes a new file and returns a path based on the first
        lookup directory.
        """
        for lookup_dir in self.lookup_dirs:
            abs_path = os.path.join(lookup_dir, relative_path)
            if os.path.exists(abs_path):
                return os.path.abspath(abs_path)

        return os.path.abspath(os.path.join(self.lookup_dirs[0], relative_path))

    def resolve_existing(self, relative_path: str) -> Optional[str]:
        """
        Resolves a relative path to an absolute path, but only if the file exists.

        Returns None if the file is not found in any lookup directory.
        """
        for lookup_dir in self.lookup_dirs:
            abs_path = os.path.join(lookup_dir, relative_path)
            if os.path.exists(abs_path):
                return os.path.abspath(abs_path)
        return None
