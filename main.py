import os
import sys
import subprocess
import argparse
import shutil
import requests
import io
import locale
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich import print as rprint

BASE_URL = "http://localhost:11434/api"
console = Console()

# =============== Git Diff Engine Functions ===============


def run_command(command: str) -> str:
    """
    Run a shell command and return its output as a string.

    Args:
        command (str): The shell command to execute

    Returns:
        str: The stripped stdout output of the command if successful,
             or an empty string if the command fails
    """
    try:
        # Using UTF-8 encoding to handle special characters in diff output
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            text=True,
            encoding="utf-8",  # Explicitly use UTF-8 instead of system default
            errors="replace",  # Replace invalid characters rather than failing
            check=False,
        )
        if result.returncode != 0:
            console.print(
                f"[yellow]Warning: Command returned non-zero exit code: {command}"
            )
            console.print(f"[red]Error: {result.stderr}")
            return ""
        return result.stdout.strip() if result.stdout else ""
    except Exception as e:
        console.print(f"[red]Error executing command: {command}")
        console.print(f"[red]Exception: {str(e)}")
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
        files = run_command(f"git diff --name-only {commit_hash}^ {commit_hash}")
        return [f for f in files.split("\n") if f]
    else:
        # For uncommitted changes
        staged = run_command("git diff --name-only --staged")
        unstaged = run_command("git diff --name-only")

        # Combine and remove duplicates
        staged_files = [f for f in staged.split("\n") if f]
        unstaged_files = [f for f in unstaged.split("\n") if f]

        all_files = set(staged_files + unstaged_files)
        return list(all_files)


def save_diff_for_file(file_info: Tuple[str, str, str]) -> str:
    """
    Save the diff for a specific file to the output directory.

    Args:
        file_info (Tuple[str, str, str]): A tuple containing:
            - file_path (str): Path to the file to generate diff for
            - output_dir (str): Directory where the diff file will be saved
            - commit_hash (str, optional): Commit hash to generate diff against.
                                         If None, generates diff for uncommitted changes.

    Returns:
        str: Path to the saved diff file, or empty string if no diff was saved
    """
    file_path, output_dir, commit_hash = file_info

    if not file_path:
        return ""

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
        console.print(f"[yellow]No changes found for: {file_path}")
        return ""

    output_path = os.path.join(output_dir, f"{safe_filename}_diff.txt")

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(diff_content)
        console.print(
            f"[green]Saved diff for: [bold]{file_path}[/bold] → {output_path}"
        )
        return output_path
    except Exception as e:
        console.print(f"[red]Error saving diff for {file_path}: {str(e)}")
        return ""


def clear_directory(directory: str) -> None:
    """
    Clear all files in the specified directory without removing the directory itself.

    Args:
        directory (str): Path to the directory to clear

    Returns:
        None
    """
    if os.path.exists(directory):
        console.print(f"[yellow]Clearing files in {directory}...")
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                console.print(f"[red]Error removing {file_path}: {e}")


def export_git_diffs(
    commit_hash: Optional[str] = None,
    output_dir: str = "temp_diffs",
    max_workers: int = 4,
) -> List[str]:
    """
    Export diffs for all changed files in parallel.

    Args:
        commit_hash (Optional[str], optional): The commit hash to get changes for.
            If None, exports diffs for uncommitted changes. Defaults to None.
        output_dir (str, optional): Directory where diff files will be saved.
            Defaults to "temp_diffs".
        max_workers (int, optional): Number of parallel threads to use for
            processing diffs. Defaults to 4.

    Returns:
        List[str]: List of paths to saved diff files
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Clear existing files in the output directory
    clear_directory(output_dir)

    # If no commit hash provided, use the latest changes
    commit_desc = f"commit: {commit_hash}" if commit_hash else "uncommitted changes"

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[bold blue]Exporting diffs for {commit_desc}..."),
        transient=False,
    ) as progress:
        task = progress.add_task("", total=None)

        # Get changed files
        files = get_changed_files(commit_hash)

        if not files:
            progress.stop()
            console.print("[yellow]No changed files found!")
            return []

        progress.update(
            task, description=f"[bold blue]Found {len(files)} changed file(s)..."
        )

        # Prepare arguments for parallel processing
        file_infos = [(file_path, output_dir, commit_hash) for file_path in files]

        # Process files in parallel
        diff_files = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i, result in enumerate(executor.map(save_diff_for_file, file_infos)):
                if result:
                    diff_files.append(result)
                progress.update(
                    task,
                    description=f"[bold blue]Processing file {i+1}/{len(files)}...",
                )

        progress.update(
            task,
            description=f"[bold green]All diffs exported ({len(diff_files)}/{len(files)} files)",
        )

    console.print(f"[bold green]All diffs exported to {os.path.abspath(output_dir)}")
    return diff_files


# =============== Ollama Functions ===============


def get_models() -> list:
    """Get all available models on the system"""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Loading models..."),
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            response = requests.get(f"{BASE_URL}/tags")

        if response.status_code == 200:
            return response.json().get("models", [])
        else:
            console.print(f"[bold red]Error: {response.status_code}")
            return []
    except requests.exceptions.ConnectionError:
        console.print("[bold red]Unable to connect to Ollama server")
        console.print(
            "[yellow]Please check if Ollama is running at http://localhost:11434"
        )
        return []


def display_models(models) -> None:
    """Display models in table format"""
    if not models:
        console.print(
            Panel(
                "[italic yellow]No models installed on the system",
                title="[bold red]Warning",
                border_style="red",
            )
        )
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.", style="dim", width=6, justify="center")
    table.add_column("Model Name", style="cyan", min_width=20)
    table.add_column("Size", style="green", justify="right")
    table.add_column("Tags", style="yellow")

    for i, model in enumerate(models, 1):
        name = model.get("name", "")
        size = f"{model.get('size', 0) / 1_000_000_000:.2f} GB"
        tags = ", ".join(model.get("tags", []))
        table.add_row(str(i), name, size, tags)

    console.print(
        Panel(table, title="[bold cyan]Installed Models", border_style="cyan")
    )


def select_model(models) -> str | None:
    """Let the user select a model"""
    if not models:
        return None

    console.print("\n[bold yellow]Please select a model (enter number or 'q' to quit):")
    choice = console.input("[bold cyan]>>> ")

    if choice.lower() == "q":
        return None

    try:
        index = int(choice) - 1
        if 0 <= index < len(models):
            return models[index]["name"]
        else:
            console.print("[bold red]Invalid number")
            return select_model(models)
    except ValueError:
        console.print("[bold red]Please enter a valid number")
        return select_model(models)


def analyze_diff_with_llm(
    model_name: str, diff_file: str, system_prompt: str = None
) -> str:
    """
    Analyze a diff file using the selected LLM model and display the result directly

    Args:
        model_name (str): Name of the Ollama model to use
        diff_file (str): Path to the diff file to analyze
        system_prompt (str, optional): System prompt to provide context

    Returns:
        str: The LLM's analysis of changes in the diff file
    """
    try:
        # Read the diff file
        with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
            diff_content = f.read()

        # Extract the original filename from the diff filename
        filename = (
            os.path.basename(diff_file).replace("_diff.txt", "").replace("__", "/")
        )

        # Prepare the prompt - modified to be more direct
        user_prompt = f"""Analyze this git diff for file '{filename}' and list the changes:
        {diff_content}
        """

        # Use a more direct system prompt
        if system_prompt is None:
            system_prompt = """
            Analyze the following Python diff. Only summarize the key components and workflow of the script, and highlight any notable implementation details or potential issues. Use the following structure only:

            Key Components and Workflow
            [bullet points about how the script works]

            Identified Issues and Solutions
            [bullet points with observations and notes]

            Keep the explanation focused and concise. Do not provide any conclusion or general commentary.

            ```diff
            [INSERT DIFF HERE]  
            ```
            """

        data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }

        console.print(f"[bold blue]Analyzing: {filename}...")

        response = requests.post(f"{BASE_URL}/chat", json=data)

        if response.status_code == 200:
            result = response.json()
            analysis = result.get("message", {}).get("content", "No analysis available")

            # Display the result directly
            console.print("\n")
            console.print(
                Panel(
                    Markdown(analysis),
                    title=f"[bold green]Analysis of {filename}",
                    border_style="green",
                    width=100,
                )
            )
            console.print(f"[green]✓ Analysis completed for: [bold]{filename}")
            return analysis
        else:
            error_msg = f"Error ({response.status_code}) analyzing {filename}"
            console.print(f"[bold red]{error_msg}")
            return error_msg

    except Exception as e:
        error_msg = f"Error processing {diff_file}: {str(e)}"
        console.print(f"[bold red]{error_msg}")
        return error_msg


# =============== Main Function ===============


def analyze_git_changes(
    model_name: str,
    commit_hash: Optional[str] = None,
    output_dir: str = "temp_diffs",
    system_prompt: str = None,
) -> None:
    """
    Analyze git changes using the specified model and output each file's analysis directly

    Args:
        model_name (str): Name of the Ollama model to use
        commit_hash (Optional[str]): Commit hash to analyze, or None for uncommitted changes
        output_dir (str): Directory to store diff files
        system_prompt (str, optional): Custom system prompt for the LLM

    Returns:
        None
    """
    # Export git diffs
    console.print(
        Panel.fit(f"[bold cyan]Step 1: Exporting Git Diffs", border_style="cyan")
    )
    diff_files = export_git_diffs(commit_hash, output_dir)

    if not diff_files:
        console.print("[yellow]No diff files were generated. Nothing to analyze.")
        return

    # Analyze each diff file
    console.print(
        Panel.fit(
            f"[bold cyan]Step 2: Analyzing {len(diff_files)} Diff Files",
            border_style="cyan",
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Analyzing files..."),
        transient=False,
    ) as progress:
        task = progress.add_task("", total=len(diff_files))

        for i, diff_file in enumerate(diff_files):
            progress.update(
                task,
                description=f"[bold blue]Analyzing file {i+1}/{len(diff_files)}: {os.path.basename(diff_file)}",
            )
            # Analyze and display result directly
            analyze_diff_with_llm(model_name, diff_file, system_prompt)
            progress.update(task, advance=1)

    console.print("\n[bold green]Analysis complete!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Git Diff Analyzer with Ollama")
    parser.add_argument("-m", "--model", help="Specify Ollama model name to use")
    parser.add_argument(
        "-c",
        "--commit",
        help="Specific commit hash to analyze (default: uncommitted changes)",
    )
    parser.add_argument(
        "--output",
        default="temp_diffs",
        help="Output directory for diff files (default: temp_diffs)",
    )
    parser.add_argument(
        "--threads", type=int, default=4, help="Number of parallel workers (default: 4)"
    )
    parser.add_argument("--prompt", help="Custom system prompt for the LLM")

    args = parser.parse_args()

    # Show header
    console.print(
        Panel.fit(
            "[bold magenta]Git Diff Analyzer with Ollama[/bold magenta]\n"
            "[cyan]Tool for analyzing git changes using LLMs",
            title="[bold green]Welcome",
            border_style="green",
        )
    )

    # Get models and display them
    models = get_models()
    display_models(models)

    if not models:
        return

    # Get commit hash if not provided
    commit_hash = args.commit
    if not commit_hash:
        # Ask the user if they want to analyze a specific commit or uncommitted changes
        console.print("\n[bold yellow]What would you like to analyze?")
        console.print("[cyan]1. Current uncommitted changes")
        console.print("[cyan]2. Specific git commit")
        choice = Prompt.ask(
            "[bold cyan]Choose an option", choices=["1", "2"], default="1"
        )

        if choice == "2":
            latest_commit = get_latest_commit_hash()
            console.print(f"[cyan]Latest commit: {latest_commit}")
            commit_hash = Prompt.ask(
                "[bold cyan]Enter commit hash", default=latest_commit
            )

    # Let user select a model
    selected_model = args.model or select_model(models)
    if not selected_model:
        console.print("[yellow]Thank you for using the service")
        return

    console.print(f"[bold green]Selected model: {selected_model}")

    # Set default system prompt if not provided
    system_prompt = args.prompt
    if not system_prompt:
        system_prompt = """Output format: markdown with filename as H1 heading, followed by bullet points of changes.
        - List what was added, removed, or modified
        - Note code structure changes, logic updates, bug fixes
        - Be direct, factual, and concise
        - No introductory or closing phrases
        - No commentary about what you're doing
        """

    # Analyze git changes
    analyze_git_changes(selected_model, commit_hash, args.output, system_prompt)

    console.print("\n[bold green]Analysis complete! Thank you for using the service!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Operation cancelled")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error: {str(e)}")
        sys.exit(1)
