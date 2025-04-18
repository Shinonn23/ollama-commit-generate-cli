import subprocess
from rich.console import Console
from typing import List, Tuple

console = Console()


def run_git_command(command: List[str]) -> Tuple[int, str, str]:
    """
    Runs a git command and returns its return code, stdout, and stderr.

    Args:
        command (List[str]): The git command and its arguments as a list of strings.
                             Example: ["git", "rev-parse", "HEAD"]

    Returns:
        Tuple[int, str, str]: A tuple containing the command's return code,
                              stdout (decoded string), and stderr (decoded string).
                              Returns (1, "", "Exception details") if an exception occurs.
    """
    try:
        # Execute the command using subprocess.run
        # capture_output=True captures stdout and stderr
        # text=True decodes stdout/stderr using encoding
        # encoding="utf-8" ensures consistent decoding, handling various characters
        # errors="replace" replaces invalid characters instead of failing
        # check=False prevents raising CalledProcessError on non-zero exit codes
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        # Optional: Log the command and its result verbosely if needed for debugging
        # console.print(f"[dim]Executing command:[/dim] [blue]{' '.join(result.args)}[/blue]")
        # console.print(f"[dim]Return Code:[/dim] {result.returncode}")
        # if result.stdout:
        #     console.print(f"[dim]Stdout:\n{result.stdout.strip()}[/dim]")
        # if result.stderr:
        #     console.print(f"[dim]Stderr:\n{result.stderr.strip()}[/dim]", style="dim red")


        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        # Handle case where 'git' command is not found
        error_msg = "Git command not found. Is Git installed and in your PATH?"
        console.print(f"[bold red]Error:[/bold red] {error_msg}")
        return 1, "", error_msg
    except Exception as e:
        # Handle other potential exceptions during execution
        error_msg = f"Exception running command {' '.join(command)}: {e}"
        console.print(f"[bold red]Error:[/bold red] {error_msg}")
        return 1, "", error_msg