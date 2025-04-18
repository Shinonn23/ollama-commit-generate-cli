import shutil
from typing import Optional
from rich.console import Console
import os
from typing import List
from _engine.git.engine import run_git_command
from rich import print as rprint

console = Console()

def get_changed_files(commit_hash: Optional[str] = None) -> List[str]:
    """
    Get list of files changed in the commit or latest uncommitted changes.

    Args:
        commit_hash (Optional[str]): Commit hash. None for uncommitted changes.

    Returns:
        List[str]: List of changed file paths. Returns an empty list on failure or no changes.
    """
    files = set()
    command_desc = (
        f"commit [yellow]{commit_hash[:8]}...[/yellow]" if commit_hash else "[yellow]uncommitted changes[/yellow]"
    )
    rprint(f"[info]Getting changed files for {command_desc}...")

    if commit_hash:
        # Specific commit: compare commit with its parent
        # Using git diff-tree --name-only is efficient for listing files in a commit
        command = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash]
        returncode, stdout, stderr = run_git_command(command)
        if returncode != 0:
            rprint(f"[error]Failed to list files for commit {commit_hash[:8]}...[/error]")
            rprint(f"[dim]Details:[/dim] [dim yellow]{stderr}[/dim yellow]")
            return []
        files.update(f for f in stdout.splitlines() if f.strip())
    else:
        # Uncommitted changes (staged + unstaged)
        # Get staged files
        staged_command = ["git", "diff", "--name-only", "--staged"]
        returncode_staged, stdout_staged, stderr_staged = run_git_command(staged_command)
        if returncode_staged != 0:
            rprint("[error]Failed to list staged files.[/error]")
            rprint(f"[dim]Details:[/dim] [dim yellow]{stderr_staged}[/dim yellow]")
            # Continue to check unstaged, don't return yet
        files.update(f for f in stdout_staged.splitlines() if f.strip())

        # Get unstaged files
        unstaged_command = ["git", "diff", "--name-only"]
        returncode_unstaged, stdout_unstaged, stderr_unstaged = run_git_command(unstaged_command)
        if returncode_unstaged != 0:
            rprint("[error]Failed to list unstaged files.[/error]")
            rprint(f"[dim]Details:[/dim] [dim yellow]{stderr_unstaged}[/dim yellow]")
            # Still return what we have, or an empty list if both failed

        files.update(f for f in stdout_unstaged.splitlines() if f.strip())

    file_list = sorted(list(files))
    if file_list:
         rprint(f"[info]Found [bold]{len(file_list)}[/bold] changed file(s).[/info]")
    else:
         rprint("[warning]No changed files detected.[/warning]")
    return file_list


def clear_directory_content(directory: str) -> bool:
    """
    Clear all files and directories within the specified directory
    without removing the directory itself. Creates the directory if it doesn't exist.

    Args:
        directory (str): Path to the directory to clear.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Ensure the directory exists
        os.makedirs(directory, exist_ok=True)
        rprint(f"[info]Ensured output directory exists: [dim]{os.path.abspath(directory)}[/dim][/info]")

        rprint(f"[info]Clearing existing content in [dim]{directory}[/dim]...")
        for item_name in os.listdir(directory):
            item_path = os.path.join(directory, item_name)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)  # Remove file or symbolic link
                    # rprint(f"[dim]Removed file: {item_path}[/dim]") # Optional: verbose removal logging
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path) # Remove directory and its contents
                    # rprint(f"[dim]Removed directory: {item_path}[/dim]") # Optional: verbose removal logging
            except Exception as e:
                rprint(f"[error]Error removing item {item_path}: {e}[/error]")
                # Continue clearing other items despite this error
        rprint("[info]Directory content cleared successfully.[/info]")
        return True
    except Exception as e:
        rprint(f"[bold red]Critical Error:[/bold red] Failed during directory preparation or clearing: {e}[/error]")
        return False
