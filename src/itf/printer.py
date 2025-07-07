# ./src/itf/printer.py
import sys

from colorama import Fore, Style, init

# Initialize colorama to auto-reset styles after each print
init(autoreset=True)

# --- Color Definitions ---
COLOR_INFO = Fore.CYAN
COLOR_SUCCESS = Fore.GREEN
COLOR_WARNING = Fore.YELLOW
COLOR_ERROR = Fore.RED
COLOR_PROMPT = Fore.MAGENTA
COLOR_HEADER = Fore.BLUE + Style.BRIGHT
# MODIFIED: Changed from a dim gray to bright yellow for better readability
COLOR_PATH = Fore.YELLOW


# --- Print Functions ---
def print_header(message, file=sys.stderr):
    print(f"{COLOR_HEADER}{message}", file=file)


def print_info(message, file=sys.stderr):
    print(f"{COLOR_INFO}{message}", file=file)


def print_success(message, file=sys.stderr):
    print(f"{COLOR_SUCCESS}{message}", file=file)


def print_warning(message, file=sys.stderr):
    print(f"{COLOR_WARNING}{message}", file=file)


def print_error(message, file=sys.stderr):
    print(f"{COLOR_ERROR}{message}", file=file)


def prompt_user(message):
    return input(f"{COLOR_PROMPT}{message} {Style.RESET_ALL}")


def print_path(path_message, file=sys.stderr):
    print(f"  {COLOR_PATH}{path_message}", file=file)


# --- Progress Bar Class ---
class ProgressBar:
    """A simple progress bar that writes to stdout."""

    def __init__(self, total, prefix="Processing:", length=40):
        self.total = total
        self.prefix = prefix
        self.length = length
        self.current = 0

    def update(self, step=1):
        """Update the progress bar."""
        self.current += step
        percent = 100 * (self.current / float(self.total))
        filled_length = int(self.length * self.current // self.total)

        # Use a more visible block character
        bar = "█" * filled_length + "-" * (self.length - filled_length)

        # Write to stdout and flush
        sys.stdout.write(f"\r{self.prefix} |{bar}| {percent:.1f}%")
        sys.stdout.flush()

    def finish(self):
        """End the progress bar with a newline."""
        sys.stdout.write("\n")
        sys.stdout.flush()
