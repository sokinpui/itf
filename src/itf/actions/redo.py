# src/itf/actions/redo.py
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


class RedoAction(Action):
    def __init__(self, args: argparse.Namespace, state_manager: StateManager):
        super().__init__(args)
        self.state_manager = state_manager

    def execute(self) -> None:
        print_header("--- Redoing last reverted operation ---")
        ops_to_redo = self.state_manager.get_operations_to_redo()
        if not ops_to_redo:
            return

        print_info(
            f"Found {len(ops_to_redo)} file(s) from the next operation to redo:"
        )
        for op in ops_to_redo:
            print_path(f"- {op['path']} (action: {op['action']})")

        redone_files, failed_files = [], []
        with NeovimManager() as manager:
            progress_bar = ProgressBar(
                total=len(ops_to_redo), prefix="Redoing files:"
            )
            progress_bar.update(0)

            for op in ops_to_redo:
                if manager.redo_file(op["path"], op["action"]):
                    redone_files.append(op["path"])
                else:
                    failed_files.append(op["path"])
                progress_bar.update()
            progress_bar.finish()

        print_header("\n--- Redo Summary ---", file=sys.stdout)
        if redone_files:
            print_success(
                f"Successfully redid {len(redone_files)} file(s):",
                file=sys.stdout,
            )
            for f in redone_files:
                print(f"  - {f}", file=sys.stdout)
        if failed_files:
            print_error(
                f"Failed to redo {len(failed_files)} file(s):", file=sys.stdout
            )
            for f in failed_files:
                print(f"  - {f}", file=sys.stdout)
