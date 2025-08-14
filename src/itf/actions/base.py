# src/itf/actions/base.py
import abc
import argparse
import os
import sys
from typing import Dict, List, Set, Tuple

from ..editor import NeovimManager
from ..printer import (
    ProgressBar,
    print_error,
    print_header,
    print_info,
    print_path,
    print_success,
    print_warning,
    prompt_user,
)
from ..path_resolver import PathResolver
from ..source import SourceProvider
from ..state_manager import StateManager


class Action(abc.ABC):
    def __init__(self, args: argparse.Namespace):
        self.args = args

    @abc.abstractmethod
    def execute(self) -> None:
        raise NotImplementedError


class ContentProcessingAction(Action):
    def __init__(
        self, args: argparse.Namespace, state_manager: StateManager, path_resolver: PathResolver
    ):
        super().__init__(args)
        self.state_manager = state_manager
        self.path_resolver = path_resolver

    def execute(self) -> None:
        source_provider = SourceProvider(self.args)
        content = source_provider.get_content()
        if not content:
            return

        file_blocks, file_actions, dirs_to_create = self._plan_changes(content)
        if not file_blocks:
            print_warning("No valid changes were generated. Nothing to do.")
            return

        if not self._confirm_and_create_directories(dirs_to_create):
            return

        self._apply_changes_in_nvim(file_blocks, file_actions)

    @abc.abstractmethod
    def _plan_changes(
        self, content: str
    ) -> Tuple[List[Tuple[str, List[str]]], Dict[str, str], Set[str]]:
        raise NotImplementedError

    @staticmethod
    def _get_file_actions_and_dirs(
        target_paths: List[str],  # Expects absolute paths
    ) -> Tuple[Dict[str, str], Set[str]]:
        file_actions = {
            fp: "create" if not os.path.exists(fp) else "modify"
            for fp in target_paths
        }
        directories_to_create = set()
        for file_path in target_paths:
            target_dir = os.path.dirname(file_path)
            if target_dir and not os.path.exists(target_dir):
                directories_to_create.add(target_dir)
        return file_actions, directories_to_create

    def _confirm_and_create_directories(self, dirs_to_create: Set[str]) -> bool:
        if not dirs_to_create:
            print_info("\nNo new directories need to be created.")
            return True

        print_info("\nThe following directories need to be created:")
        for d in sorted(list(dirs_to_create)):
            print_path(f"- {d}")

        response = prompt_user(
            "Do you want to create all these directories? (y/N):"
        ).lower()
        if response != "y":
            print_warning("Directory creation declined. Exiting.")
            return False

        print_info("\nCreating directories...")
        for d in sorted(list(dirs_to_create)):
            try:
                os.makedirs(d, exist_ok=True)
                print_success(f"  -> Created: {d}")
            except OSError as e:
                print_error(f"  -> Error creating directory '{d}': {e}")
                print_error("Aborting due to directory creation failure.")
                return False
        return True

    def _apply_changes_in_nvim(
        self, file_blocks: List[Tuple[str, List[str]]], file_actions: Dict[str, str]
    ) -> None:
        updated_files, failed_files = [], []
        with NeovimManager() as manager:
            progress_bar = ProgressBar(
                total=len(file_blocks), prefix="Updating buffers:"
            )
            progress_bar.update(0)

            for file_path, content_lines in file_blocks:
                if manager.update_buffer(file_path, content_lines):
                    updated_files.append(file_path)
                else:
                    failed_files.append(file_path)
                progress_bar.update()
            progress_bar.finish()

            print_header("\n--- Update Summary ---", file=sys.stdout)
            if updated_files:
                print_success(
                    f"Successfully updated {len(updated_files)} file(s) in Neovim:",
                    file=sys.stdout,
                )
                for f in updated_files:
                    print(f"  - {f}", file=sys.stdout)
            if failed_files:
                print_error(
                    f"Failed to process {len(failed_files)} file(s):", file=sys.stdout
                )
                for f in failed_files:
                    print(f"  - {f}", file=sys.stdout)

            if updated_files:
                if self.args.save:
                    manager.save_all_buffers()
                    successful_ops = [
                        {"path": f, "action": file_actions[f]}
                        for f in updated_files
                    ]
                    self.state_manager.write(successful_ops)
                else:
                    print_warning(
                        "\nChanges are not saved to disk. Use -s/--save to persist changes.",
                        file=sys.stdout,
                    )
                    print_warning(
                        "Revert will not be available for this operation.",
                        file=sys.stdout,
                    )
