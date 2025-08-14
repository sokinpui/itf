# src/itf/app.py
import argparse
import sys

from .actions import AutoAction, BlockAction, DiffAction, DiffFixAction, RevertAction
from .actions.base import Action
from .path_resolver import PathResolver
from .printer import print_warning
from .state_manager import StateManager


class ItfApp:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.state_manager = StateManager()
        self.path_resolver = PathResolver(args.lookup_dir)

    def run(self):
        try:
            action = self._create_action()
            if action:
                action.execute()
        except (EOFError, KeyboardInterrupt):
            print_warning("\nOperation cancelled by user. Exiting.")
            sys.exit(0)

    def _create_action(self) -> Action | None:
        if self.args.revert:
            return RevertAction(self.args, self.state_manager)
        if self.args.output_diff_fix:
            return DiffFixAction(self.args, self.path_resolver)
        if self.args.auto:
            return AutoAction(self.args, self.state_manager, self.path_resolver)
        if self.args.diff:
            return DiffAction(self.args, self.state_manager, self.path_resolver)
        # Default action is block mode
        return BlockAction(self.args, self.state_manager, self.path_resolver)
