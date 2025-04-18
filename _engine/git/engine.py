# Standard Library Imports
import os
from typing import List, Optional, Tuple

# Third-Party Library Imports
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint # Use rich.print for consistent styling

# Build-in Functions And Class Import
from .command import run_git_command
from .files_controller import get_changed_files, clear_directory_content


# --- Configuration ---
# Default directory to save diff files
DEFAULT_DIFF_OUTPUT_DIR = "exported_git_diffs"
# Default number of worker threads for parallel processing
DEFAULT_MAX_WORKERS = os.cpu_count() or 4


# --- Initialize Rich Console ---
# Create a global console instance for consistent output
console = Console()

def get_latest_commit_hash() -> Optional[str]:
    """
    Get the latest commit hash from the git repository.

    Returns:
        Optional[str]: The SHA-1 hash of the most recent commit, or None on failure.
    """
    rprint("[info]Attempting to get the latest commit hash...")
    # Use the new run_git_command
    returncode, stdout, stderr = run_git_command(["git", "rev-parse", "HEAD"])

    if returncode != 0:
        rprint(f"[error]Failed to get latest commit hash.[/error]")
        rprint(f"[dim]Details:[/dim] [dim yellow]{stderr}[/dim yellow]")
        return None

    commit_hash = stdout.strip()
    if commit_hash:
        rprint(f"[info]Latest commit hash found: [yellow]{commit_hash}[/yellow][/info]")
        return commit_hash
    else:
        rprint("[warning]Git command 'git rev-parse HEAD' returned empty output.[/warning]")
        return None


# --- Diff Handling Function (for parallel processing) ---

def generate_and_save_diff(file_info: Tuple[str, str, Optional[str]]) -> Optional[str]:
    """
    Generates and saves the git diff for a specific file.
    Designed to be run in a thread pool.

    Args:
        file_info (Tuple[str, str, Optional[str]]): A tuple containing:
            - file_path (str): Path to the file to generate diff for.
            - output_dir (str): Directory where the diff file will be saved.
            - commit_hash (str, optional): Commit hash to generate diff against.
              If None, generates diff for uncommitted changes.

    Returns:
        Optional[str]: Path to the saved diff file, or None if no diff was saved or an error occurred.
                       Returns None if git diff returns an empty string.
    """
    file_path, output_dir, commit_hash = file_info

    if not file_path or not output_dir:
        rprint(f"[error]Invalid input for generate_and_save_diff: {file_info}[/error]")
        return None

    # Create a safe filename by replacing directory separators
    safe_filename = file_path.replace(os.sep, "__")

    # Determine the correct git diff command
    diff_command_list: List[str] = ["git", "diff"]

    if commit_hash:
        # Diff between the commit and its parent (or against empty tree for initial commit)
        # Using {commit_hash}^..{commit_hash} is explicit for comparing a commit to its parent
        # git diff commit^ commit -- file works for most cases
        # git diff 4b825dc642cb6eb9a060e54bf8d69288fbee4904 commit -- file handles initial commit
        # We can use the specific hash directly for committed files
        diff_command_list.extend([f"{commit_hash}^", commit_hash, "--", file_path])
    else:
        # Uncommitted changes (working tree vs index or HEAD)
        # git diff --staged -- file for staged changes
        # git diff -- file for unstaged changes
        # We need to generate both diffs and combine them if the file is both staged and unstaged
        # Or more simply, just use git diff -- file which shows unstaged changes relative to index,
        # and git diff --staged -- file which shows staged changes relative to HEAD.
        # The standard practice is to get diffs relative to HEAD for staged and index for unstaged.
        # A simpler approach for uncommitted is `git diff HEAD -- file`. This shows ALL uncommitted changes for the file.
        # Let's use `git diff HEAD -- file` as it gives the combined view relative to the last commit.
        diff_command_list.extend(["HEAD", "--", file_path])


    returncode, diff_content, stderr = run_git_command(diff_command_list)

    if returncode != 0:
        rprint(f"[error]Failed to generate diff for [bold]{file_path}[/bold].[/error]")
        rprint(f"[dim]Command:[/dim] [dim blue]{' '.join(diff_command_list)}[/dim blue]")
        rprint(f"[dim]Details:[/dim] [dim yellow]{stderr}[/dim yellow]")
        return None # Indicate failure

    if not diff_content.strip():
        # console.print(f"[dim]No relevant diff found for: {file_path}[/dim]") # Too verbose for progress
        return None # Indicate no diff was generated/needed

    # Construct the full output path
    output_path = os.path.join(output_dir, f"{safe_filename}_diff.txt")

    try:
        # Ensure parent directory exists for the output file (important if file_path was nested)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(diff_content)
        # rprint(f"[green]Saved diff for: [bold]{file_path}[/bold][/green]") # Too verbose for progress
        return output_path # Return the path on success
    except Exception as e:
        rprint(f"[error]Error saving diff for [bold]{file_path}[/bold]: {str(e)}[/error]")
        return None # Indicate save failure


# --- Main Export Logic ---

def export_git_diffs(
    commit_hash: Optional[str] = None,
    output_dir: str = DEFAULT_DIFF_OUTPUT_DIR,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> List[str]:
    """
    Export diffs for changed files in parallel using Rich progress.

    Args:
        commit_hash (Optional[str]): The commit hash to diff against its parent.
                                     Set to None to export diffs for uncommitted changes
                                     relative to the latest commit (HEAD).
        output_dir (str): Directory to save diff files. Will be created if it doesn't exist,
                          and its contents will be cleared.
        max_workers (int): Number of parallel threads to use for generating and saving diffs.

    Returns:
        List[str]: List of paths to successfully saved diff files. Returns an empty list
                   if no files were changed or if preparation fails.
    """
    # --- 1. Preparation ---
    if not clear_directory_content(output_dir):
        rprint("[bold red]Aborting:[/bold red] Directory preparation failed.")
        return []

    commit_desc_rich = (
        f"commit [yellow]{commit_hash}[/yellow]"
        if commit_hash
        else "[yellow]uncommitted changes (vs HEAD)[/yellow]"
    )
    rprint(f"[info]Targeting {commit_desc_rich} for diff export.[/info]")


    # --- 2. Get Changed Files ---
    files_to_process = get_changed_files(commit_hash)

    if not files_to_process:
        rprint("[warning]No changed files found to export diffs for. Exiting.[/warning]")
        return []

    rprint(
        f"[info]Preparing to export diffs for [bold]{len(files_to_process)}[/bold] file(s) using [bold]{max_workers}[/bold] worker(s)...[/info]"
    )

    # --- 3. Parallel Processing with Rich Progress ---
    saved_diff_files: List[str] = []
    failed_files: List[Tuple[str, str]] = [] # Store file_path and error message

    # Prepare the list of file_info tuples for the workers
    file_infos_for_workers = [(file_path, output_dir, commit_hash) for file_path in files_to_process]

    # Configure Rich Progress Bar
    export_progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"), # Separator dot
        TextColumn("Processed [progress.completed] of [progress.total]"),
        TextColumn("•"), # Separator dot
        TimeElapsedColumn(),
        SpinnerColumn("simpleDots"), # Add a spinner
        console=console,
        transient=True,  # Progress bar disappears after completion
        redirect_stdout=True, # Redirect print statements within threads to the progress bar
        redirect_stderr=True,
    )

    try:
        with export_progress as progress:
            # Add the main task to the progress bar
            task_id = progress.add_task(
                f"[cyan]Exporting diffs[/cyan]...", total=len(files_to_process)
            )

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Map futures back to their original file paths
                future_to_filepath = {
                    executor.submit(generate_and_save_diff, (file_path, output_dir, commit_hash)): file_path
                    for file_path, output_dir, commit_hash in file_infos_for_workers
                }

                # Process results as they become available
                for future in as_completed(future_to_filepath):
                    original_file_path = future_to_filepath[future]
                    try:
                        saved_path = future.result() # Get the result from the thread
                        if saved_path:
                            saved_diff_files.append(saved_path)
                            # You could add a temporary update to the description here, but it might flicker
                            # progress.update(task_id, description=f"[cyan]Exporting diffs[/cyan] ([green]Saved {os.path.basename(saved_path)}[/green])...")
                        # If saved_path is None, it means no diff was generated or an error occurred
                        # Errors within generate_and_save_diff are printed by that function
                        # We don't need to explicitly add to failed_files here if the error is printed inside
                        # If we wanted to collect errors for a final report, we'd modify generate_and_save_diff
                        # to return a specific error indicator or message on failure.
                        # For now, rely on the function printing its own errors.
                    except Exception as exc:
                         # This catches unexpected exceptions from the thread
                        failed_files.append((original_file_path, str(exc)))
                        rprint(f"[bold red]Thread Error:[/bold red] Processing [bold]{original_file_path}[/bold] failed due to an unexpected exception: {exc}")


                    # Always advance the progress bar, whether success, no diff, or error
                    progress.update(task_id, advance=1)

    except Exception as e:
        rprint(f"\n[bold red]Critical Error:[/bold red] An unrecoverable error occurred during parallel diff generation: {e}[/error]")
        # If a critical error happens here, the state of saved_diff_files might be incomplete
        # We still return what was saved up to this point, but the user is alerted.


    # --- 4. Final Summary ---
    rprint("\n[bold blue]✨ Diff Export Summary ✨[/bold blue]")
    rprint("[blue]" + "=" * 78 + "[/blue]") # Rich separator

    total_files_attempted = len(files_to_process)
    successfully_saved_count = len(saved_diff_files)
    failed_count = total_files_attempted - successfully_saved_count # Simple count based on whether a file was saved

    if failed_files:
         rprint("[bold yellow]⚠️ Some files encountered errors or did not generate diffs:[/bold yellow]")
         # Detailed logging of failed files is handled by generate_and_save_diff for now
         rprint(f"[dim](See messages above for specific file errors)[/dim]")
    elif successfully_saved_count < total_files_attempted:
         rprint("[warning]Some files did not result in a saved diff (e.g., no changes, or silent save error).[/warning]")


    # Use a Rich Table for a nice summary output
    summary_table = Table(title="Export Results")
    summary_table.add_column("Metric", style="cyan", justify="right")
    summary_table.add_column("Count", style="magenta", justify="left")

    summary_table.add_row("Total changed files found", str(total_files_attempted))
    summary_table.add_row("Diff files successfully saved", str(successfully_saved_count), style="bold green" if successfully_saved_count == total_files_attempted else "bold yellow")
    summary_table.add_row("Files with no saved diff", str(failed_count), style="bold red" if failed_count > 0 else "dim") # This count is based on saved_path being None


    rprint(summary_table)
    rprint(f"[info]Output directory: [link=file://{os.path.abspath(output_dir)}]{os.path.abspath(output_dir)}[/link][/info]")
    rprint("[blue]" + "=" * 78 + "[/blue]")

    return saved_diff_files


# --- Example Usage ---
if __name__ == "__main__":
    # Set up some directories for the examples
    uncommitted_dir = os.path.join(DEFAULT_DIFF_OUTPUT_DIR, "uncommitted")
    commit_dir = os.path.join(DEFAULT_DIFF_OUTPUT_DIR, "latest_commit")
    specific_commit_dir = os.path.join(DEFAULT_DIFF_OUTPUT_DIR, "specific_mock_commit")


    # Example 1: Analyze uncommitted changes
    rprint(Panel("[bold blue]🚀 Analyzing Uncommitted Changes[/bold blue]", expand=False))
    uncommitted_diffs = export_git_diffs(
        commit_hash=None, output_dir=uncommitted_dir
    )
    # rprint(f"\n[info]Uncommitted diff files created:[/info] {uncommitted_diffs}\n") # Optional: print list


    rprint("\n" + "-" * 80 + "\n") # Separator

    # Example 2: Analyze latest commit
    rprint(Panel("[bold blue]🎯 Analyzing Latest Commit[/bold blue]", expand=False))
    latest_commit = get_latest_commit_hash()
    if latest_commit:
        commit_diffs = export_git_diffs(
            commit_hash=latest_commit, output_dir=commit_dir
        )
        # rprint(f"\n[info]Latest commit diff files created:[/info] {commit_diffs}\n") # Optional: print list
    else:
        rprint("[bold yellow]Skipping latest commit analysis:[/bold yellow] Could not determine latest commit hash.")

    rprint("\n" + "-" * 80 + "\n") # Separator

    # Example 3: Analyze a specific (mock) commit
    # NOTE: This requires a real commit hash to work.
    # Replace 'your_actual_commit_hash_here' with a real hash from your repo's history.
    # If you run this in a fresh repo, there might not be enough commits.
    mock_commit_hash = "HEAD^" # Example: Diff against the commit before HEAD
    rprint(Panel(f"[bold blue]🧪 Analyzing Specific Commit ({mock_commit_hash})[/bold blue]", expand=False))
    # You'll need at least 2 commits for HEAD^ to exist
    specific_commit_diffs = export_git_diffs(
       commit_hash=mock_commit_hash, output_dir=specific_commit_dir
    )
    # rprint(f"\n[info]Specific commit diff files created:[/info] {specific_commit_diffs}\n") # Optional: print list