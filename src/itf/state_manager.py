# src/itf/state_manager.py
import datetime
import json
import os
from typing import Dict, List, Optional

from .printer import print_error, print_info, print_warning

STATE_FILE_NAME = ".itf_state.json"


class StateManager:
    def __init__(self):
        self.state_path = os.path.join(os.getcwd(), STATE_FILE_NAME)
        self.state = self._load()

    def _load(self) -> Dict:
        if not os.path.exists(self.state_path):
            return {"history": [], "current_index": -1}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Basic validation
            if "history" in state and "current_index" in state:
                return state
            print_warning("State file is malformed. Starting fresh.")
            return {"history": [], "current_index": -1}
        except (IOError, json.JSONDecodeError) as e:
            print_error(f"Failed to read or parse state file '{self.state_path}': {e}")
            return {"history": [], "current_index": -1}

    def _save(self) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except IOError as e:
            print_error(f"Failed to write state file '{self.state_path}': {e}")

    def write(self, operations: List[Dict[str, str]]) -> None:
        # Truncate any "redo" history
        self.state["history"] = self.state["history"][: self.state["current_index"] + 1]

        new_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "operations": sorted(operations, key=lambda x: x["path"]),
        }
        self.state["history"].append(new_entry)
        self.state["current_index"] += 1
        self._save()
        print_info(f"\nSaved run state for revertability to '{STATE_FILE_NAME}'")

    def get_operations_to_revert(self) -> Optional[List[Dict[str, str]]]:
        if self.state["current_index"] < 0:
            print_error(f"No history found in '{STATE_FILE_NAME}'. Nothing to revert.")
            return None

        ops_entry = self.state["history"][self.state["current_index"]]
        self.state["current_index"] -= 1
        self._save()
        return ops_entry.get("operations", [])

    def get_operations_to_redo(self) -> Optional[List[Dict[str, str]]]:
        next_index = self.state["current_index"] + 1
        if next_index >= len(self.state["history"]):
            print_error("No operations to redo. Already at the latest change.")
            return None

        self.state["current_index"] = next_index
        ops_entry = self.state["history"][self.state["current_index"]]
        self._save()
        return ops_entry.get("operations", [])
