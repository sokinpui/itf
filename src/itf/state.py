# ./src/itf/state.py
import datetime
import json
import os
from typing import List, Dict

from .printer import print_error, print_info, print_warning

STATE_FILE_NAME = ".itf_state.json"


def write_last_run_state(operations: List[Dict[str, str]]):
    """
    Writes the state of the last run to a file.

    Args:
        operations: A list of dictionaries, where each dictionary contains
                    the 'path' and 'action' ('create' or 'modify') for a file.
    """
    state_path = os.path.join(os.getcwd(), STATE_FILE_NAME)
    state = {
        "last_run": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "operations": sorted(operations, key=lambda x: x["path"]),
        }
    }
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print_info(f"\nSaved run state for revertability to '{STATE_FILE_NAME}'")
    except IOError as e:
        print_error(f"Failed to write state file '{state_path}': {e}")


def read_last_run_state() -> List[Dict[str, str]]:
    """
    Reads the list of file operations from the last run state file.
    """
    state_path = os.path.join(os.getcwd(), STATE_FILE_NAME)
    if not os.path.exists(state_path):
        print_error(f"State file '{STATE_FILE_NAME}' not found. Cannot revert.")
        return []

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        operations = state.get("last_run", {}).get("operations", [])
        if not operations:
            print_warning("No operations found in the last run state.")
        return operations
    except (IOError, json.JSONDecodeError) as e:
        print_error(f"Failed to read or parse state file '{state_path}': {e}")
        return []

