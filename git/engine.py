import os
import subprocess
import argparse
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple


def run_command(command: str) -> str:
    """
    Run a shell command and return its output as a string.

    Args:
        command (str): The shell command to execute

    Returns:
        str: The stripped stdout output of the command if successful,
             or an empty string if the command fails

    Note:
        This function executes commands in a shell environment, which may pose
        security risks if used with untrusted input.
    """
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"Warning: Command returned non-zero exit code: {command}")
            print(f"Error: {result.stderr}")
            return ""
        return result.stdout.strip()
    except Exception as e:
        print(f"Error executing command: {command}")
        print(f"Exception: {str(e)}")
        return ""


def get_latest_commit_hash() -> str:
    """
    Get the latest commit hash from the git repository.

    Returns:
        str: The SHA-1 hash of the most recent commit in the current branch.
             Returns an empty string if the command fails.
    """
    return run_command("git rev-parse HEAD")


def get_changed_files(commit_hash: Optional[str] = None) -> List[str]:
    """
    Get list of files changed in the commit or latest uncommitted changes.

    Args:
        commit_hash (Optional[str], optional): The commit hash to get changes for.
            If None, returns uncommitted changes. Defaults to None.

    Returns:
        List[str]: A list of file paths that were changed in the specified commit
            or in the current working directory if no commit is specified.
            Empty strings are filtered out.
    """
    if commit_hash:
        # For a specific commit
        return run_command(f"git diff --name-only {commit_hash}^ {commit_hash}").split(
            "\n"
        )
    else:
        # For uncommitted changes
        staged = run_command("git diff --name-only --staged")
        unstaged = run_command("git diff --name-only")

        # Combine and remove duplicates
        all_files = set(staged.split("\n") + unstaged.split("\n"))
        # Remove empty strings
        return [f for f in all_files if f]


def save_diff_for_file(file_info: Tuple[str, str, str]) -> None:
    """
    Save the diff for a specific file to the output directory.

    Args:
        file_info (Tuple[str, str, str]): A tuple containing:
            - file_path (str): Path to the file to generate diff for
            - output_dir (str): Directory where the diff file will be saved
            - commit_hash (str, optional): Commit hash to generate diff against.
                                         If None, generates diff for uncommitted changes.

    Returns:
        None

    Note:
        The diff file will be named using a safe version of the file path,
        with directory separators replaced by double underscores.
    """
    file_path, output_dir, commit_hash = file_info

    if not file_path:
        return

    # Create a safe filename
    safe_filename = file_path.replace("/", "__").replace("\\", "__")

    # Generate diff command based on whether we have a commit hash
    if commit_hash:
        diff_command = f'git diff {commit_hash}^ {commit_hash} -- "{file_path}"'
    else:
        # Check if file is staged
        is_staged = file_path in run_command("git diff --name-only --staged").split(
            "\n"
        )
        if is_staged:
            diff_command = f'git diff --staged -- "{file_path}"'
        else:
            diff_command = f'git diff -- "{file_path}"'

    diff_content = run_command(diff_command)

    if not diff_content:
        print(f"No changes found for: {file_path}")
        return

    output_path = os.path.join(output_dir, f"{safe_filename}_diff.txt")

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(diff_content)
        print(f"Saved diff for: {file_path} → {output_path}")
    except Exception as e:
        print(f"Error saving diff for {file_path}: {str(e)}")


def clear_directory(directory: str) -> None:
    """
    Clear all files in the specified directory without removing the directory itself.

    Args:
        directory (str): Path to the directory to clear

    Returns:
        None
    """
    if os.path.exists(directory):
        print(f"Clearing files in {directory}...")
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Error removing {file_path}: {e}")


def export_git_diffs(
    commit_hash: Optional[str] = None,
    output_dir: str = "temp_diffs",
    max_workers: int = 4,
) -> None:
    """
    Export diffs for all changed files in parallel.

    This function identifies changed files in a git repository and saves
    individual diff files for each changed file to the specified output directory.
    All existing files in the output directory are cleared before new diffs are created.

    Args:
        commit_hash (Optional[str], optional): The commit hash to get changes for.
            If None, exports diffs for uncommitted changes. Defaults to None.
        output_dir (str, optional): Directory where diff files will be saved.
            Defaults to "temp_diffs".
        max_workers (int, optional): Number of parallel threads to use for
            processing diffs. Defaults to 4.

    Returns:
        None

    Note:
        The output directory will be created if it doesn't exist.
        All existing files in the output directory will be removed before new diffs are saved.
        Diff files are named using a safe version of the original file path.
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Clear existing files in the output directory
    clear_directory(output_dir)

    # If no commit hash provided, use the latest changes
    if not commit_hash:
        print("Exporting diffs for uncommitted changes...")
    else:
        print(f"Exporting diffs for commit: {commit_hash}")

    # Get changed files
    files = get_changed_files(commit_hash)

    if not files or (len(files) == 1 and not files[0]):
        print("No changed files found!")
        return

    print(f"Found {len(files)} changed file(s)")

    # Prepare arguments for parallel processing
    file_infos = [(file_path, output_dir, commit_hash) for file_path in files]

    # Process files in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(save_diff_for_file, file_infos)

    print(f"All diffs exported to {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export git diffs by file")
    parser.add_argument(
        "--commit",
        help="Specific commit hash to export diffs for (default: uncommitted changes)",
    )
    parser.add_argument(
        "--output",
        default="temp_diffs",
        help="Output directory for diff files (default: temp_diffs)",
    )
    parser.add_argument(
        "--threads", type=int, default=4, help="Number of parallel workers (default: 4)"
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not clear existing files in the output directory before exporting",
    )

    args = parser.parse_args()

    export_git_diffs(args.commit, args.output, args.threads)
