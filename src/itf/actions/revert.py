# src/itf/actions/revert.py
import argparse
import sys

from ..editor import NeovimManager
from ..printer import (
    ProgressBar,
    print_error,
    print_header,
    print_info,
    print_path,
    print_success,
    print_warning,
)
from ..state_manager import StateManager
from .base import Action


class RevertAction(Action):
    def __init__(self, args: argparse.Namespace, state_manager: StateManager):
        super().__init__(args)
        self.state_manager = state_manager

    def execute(self) -> None:
        print_header("--- Reverting last operation ---")
        ops_to_revert = self.state_manager.get_operations_to_revert()
        if not ops_to_revert:
            return

        print_info(
            f"Found {len(ops_to_revert)} file(s) from the last operation to revert:"
        )
        for op in ops_to_revert:
            print_path(f"- {op['path']} (action: {op['action']})")

        reverted_files, failed_files = [], []
        with NeovimManager() as manager:
            progress_bar = ProgressBar(
                total=len(ops_to_revert), prefix="Reverting files:"
            )
            progress_bar.update(0)

            for op in ops_to_revert:
                if manager.revert_file(op["path"], op["action"]):
                    reverted_files.append(op["path"])
                else:
                    failed_files.append(op["path"])
                progress_bar.update()
            progress_bar.finish()

        print_header("\n--- Revert Summary ---", file=sys.stdout)
        if reverted_files:
            print_success(
                f"Successfully reverted {len(reverted_files)} file(s):",
                file=sys.stdout,
            )
            for f in reverted_files:
                print(f"  - {f}", file=sys.stdout)
        if failed_files:
            print_error(
                f"Failed to revert {len(failed_files)} file(s):", file=sys.stdout
            )
            for f in failed_files:
                print(f"  - {f}", file=sys.stdout)
