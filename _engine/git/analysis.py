import typing
from typing import Optional, List
import os
import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.theme import Theme
import time # Import time for potential delays if needed, though Progress handles updates well

# Assuming _engine and _data are structured correctly relative to this script
# If not, adjust the import paths accordingly
try:
    from _engine.git.engine import export_git_diffs
    from _data.ollama import BASE_URL, SYSTEM_PROMPT
    from _types.model import FileChange as TypesFileChange
    
except ImportError:
    # Provide dummy implementations or raise clearer errors if modules are missing
    print("Warning: Could not import project-specific modules. Using placeholders.")
    BASE_URL = "http://localhost:11434/api" # Example placeholder
    SYSTEM_PROMPT = "You are a helpful assistant." # Example placeholder

    def export_git_diffs(commit_hash, output_dir):
        print(f"Placeholder: Pretending to export diffs for {commit_hash or 'uncommitted'} to {output_dir}")
        # Create dummy files for testing
        os.makedirs(output_dir, exist_ok=True)
        dummy_files = []
        for i in range(3):
             fname = os.path.join(output_dir, f"dummy__file_{i}_diff.txt")
             with open(fname, "w") as f:
                 f.write(f"--- a/dummy/file_{i}.py\n+++ b/dummy/file_{i}.py\n@@ -1,1 +1,1 @@\n-old line\n+new line {i}")
             dummy_files.append(fname)
        return dummy_files

    class FileChange: # Dummy Pydantic model for schema used as fallback
        @staticmethod
        def model_json_schema():
            # This should ideally return the actual JSON schema expected by the API
            # For Ollama's JSON mode, it expects a structure.
            # Example placeholder schema (adjust based on actual FileChange model):
            return {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "changes": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["summary", "changes"]
            }


# Custom theme for consistent styling
custom_theme = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "highlight": "magenta",
    }
)

console = Console(theme=custom_theme)


def analyze_diff_with_llm(
    model_name: str, diff_file: str, system_prompt: Optional[str] = None
) -> str:
    """
    Analyze a diff file using the selected LLM model.
    Handles API communication and returns the analysis content or error message.

    Args:
        model_name (str): Name of the Ollama model to use
        diff_file (str): Path to the diff file to analyze
        system_prompt (str, optional): System prompt to provide context

    Returns:
        str: The LLM's analysis of changes or an error message prefixed with "Error:".
             Success messages for individual files are printed directly to console.
    """
    filename = os.path.basename(diff_file).replace("_diff.txt", "").replace("__", "/")
    try:
        # Read the diff file
        with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
            diff_content = f.read()

        # Prepare the prompt for summarizing git diff for commit preparation
        user_prompt = f"""
        Summarize this git diff for file: '{filename}' to prepare for a commit message.

        DIFF CONTENT:
        {diff_content}

        Please provide a concise summary of all changes in this diff, focusing on what was modified, added, or removed.
        Keep it brief but informative enough to use as a basis for a good commit message.
        Output *only* the raw analysis string, without any introduction or extra formatting.
        """

        # Use a more direct system prompt
        effective_system_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT

        # Data payload for Ollama API
        # Note: Ollama's JSON mode needs the *response* to conform to the schema.
        # The prompt itself instructs the LLM, but the 'format' parameter enforces structure.
        data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": effective_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
             # Ensure TypesFileChange has a Pydantic schema if using format="json"
             # If TypesFileChange isn't a Pydantic model or format isn't desired, remove/comment out 'format'
            # "format": "json", # Removed as the prompt asks for raw string, not specific JSON
        }

        # If you intend to use JSON format, ensure TypesFileChange is a Pydantic model
        # and the LLM is prompted to produce JSON matching TypesFileChange.model_json_schema()
        # For now, assuming raw text output based on the user_prompt instruction.
        # If JSON mode *is* desired:
        # 1. Uncomment the "format": "json" line below.
        # 2. Ensure TypesFileChange is a Pydantic model with a .model_json_schema() method.
        # 3. Adjust the user_prompt to explicitly ask for JSON output matching the schema.
        # data["format"] = "json" # Example if using JSON mode

        response = requests.post(f"{BASE_URL}/chat", json=data, timeout=120) # Added timeout

        # --- Processing Response ---
        # Clear potential progress bar remnants from the previous line
        console.print("\r" + " " * console.width, end="\r")

        if response.status_code == 200:
            result = response.json()
            # Adjust access based on whether 'format' was json or not
            if "format" in data and data["format"] == "json":
                 # If JSON mode was used, Ollama nests the JSON string within 'content'
                 # You might need to parse it: json.loads(result.get("message", {}).get("content", "{}"))
                 analysis = result.get("message", {}).get("content", '{"summary": "No analysis available", "changes": []}')
                 # Potentially parse 'analysis' if it's a JSON string
            else:
                 # Raw text mode
                 analysis = result.get("message", {}).get("content", "No analysis available")


            # Print success message for this file
            console.print(f"[green]✓ Analysis successful for:[/green] [bold cyan]{filename}[/bold cyan]")
            return analysis.strip() # Return the core analysis content

        else:
            error_detail = response.text # Get more error detail
            error_msg = f"Error: API Error ({response.status_code}) analyzing {filename}. Details: {error_detail}"
            # Print error message for this file
            console.print(f"[bold red]✗ Analysis failed for:[/bold red] [yellow]{filename}[/yellow] (Status: {response.status_code})")
            return error_msg # Return the error message

    except FileNotFoundError:
        console.print("\r" + " " * console.width, end="\r")
        error_msg = f"Error: Diff file not found: {diff_file}"
        console.print(f"[bold red]✗ Error processing {filename}: File not found.")
        return error_msg
    except requests.exceptions.RequestException as e:
        console.print("\r" + " " * console.width, end="\r")
        error_msg = f"Error: Network or API request failed for {filename}: {str(e)}"
        console.print(f"[bold red]✗ Network/API Error for {filename}: {e}")
        return error_msg
    except Exception as e:
        # Catch other potential exceptions during file reading or processing
        console.print("\r" + " " * console.width, end="\r")
        error_msg = f"Error: An unexpected error occurred processing {diff_file}: {str(e)}"
        console.print(f"[bold red]✗ Unexpected Error processing {filename}: {e}")
        return error_msg


def analyze_git_changes(
    model_name: str,
    commit_hash: Optional[str] = None,
    output_dir: str = "temp_diffs",
    system_prompt: Optional[str] = None,
) -> List[typing.Tuple[str, str]]:
    """
    Analyzes git changes using the specified model, displaying progress,
    and returns a list of filenames and their analysis results (or errors).

    Args:
        model_name (str): Name of the Ollama model to use.
        commit_hash (Optional[str]): Commit hash to analyze, or None for uncommitted changes.
        output_dir (str): Directory to store temporary diff files.
        system_prompt (str, optional): Custom system prompt for the LLM.

    Returns:
        List[Tuple[str, str]]: A list where each tuple contains:
            (filename, analysis_result_or_error_string).
            Error strings will start with "Error:".
    """
    results = [] # To store (filename, analysis) tuples

    # --- Step 1: Export Diffs ---
    console.print(Panel("[bold cyan]Step 1: Exporting Git Diffs[/bold cyan]", expand=False))
    try:
        diff_files = export_git_diffs(commit_hash, output_dir)
        if not diff_files:
            console.print("[yellow]No diff files were generated. Nothing to analyze.")
            return results
        console.print(f"[info]Found {len(diff_files)} changed files to analyze.")

    except Exception as e:
        console.print(f"[error]Failed to export git diffs: {e}")
        return results # Return empty results if diff export fails

    # --- Step 2: Analyze Diffs with Progress Bar ---
    console.print(Panel(f"[bold cyan]Step 2: Analyzing {len(diff_files)} Diff Files using '{model_name}'[/bold cyan]", expand=False))

    # Configure Rich Progress
    analysis_progress = Progress(
        SpinnerColumn(),                               # Animated spinner
        TextColumn("[progress.description]{task.description}"), # Text description (e.g., "Analyzing file X...")
        BarColumn(),                                   # Progress bar
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), # Percentage complete
        TextColumn("({task.completed}/{task.total})"),  # Files completed / total files
        TimeElapsedColumn(),                           # Time elapsed
        console=console,                               # Use our themed console
        transient=False,                                # Keep the progress bar visible after completion
    )

    with analysis_progress:
        # Add a task to the progress bar
        task_id = analysis_progress.add_task(
            f"Initializing analysis...", total=len(diff_files)
        )

        for i, diff_file in enumerate(diff_files):
            # Extract filename for display and storage
            filename = os.path.basename(diff_file).replace("_diff.txt", "").replace("__", "/")

            # Update progress bar description for the current file
            analysis_progress.update(task_id, description=f"Analyzing: [highlight]{filename}[/highlight]")

            # Analyze the file using the LLM function
            # The analyze_diff_with_llm function now prints its own status (success/failure) per file
            analysis_result = analyze_diff_with_llm(
                model_name, diff_file, system_prompt
            )

            # Store the result (analysis or error message)
            results.append((filename, analysis_result))

            # Advance the progress bar after processing the file
            # Add a small delay if API calls are too fast, to make spinner visible
            # time.sleep(0.1)
            analysis_progress.update(task_id, advance=1)

        # Update progress description upon completion
        analysis_progress.update(task_id, description="[bold green]Analysis Complete![/bold green]")

    # --- Final Summary ---
    console.print("\n" + "="*30 + " Analysis Summary " + "="*30)
    success_count = sum(1 for _, result in results if not result.startswith("Error:"))
    error_count = len(results) - success_count

    console.print(f"[success]Successfully analyzed: {success_count} files")
    if error_count > 0:
        console.print(f"[error]Failed to analyze: {error_count} files")
        console.print("[yellow]Files with errors:[/yellow]")
        for filename, result in results:
            if result.startswith("Error:"):
                console.print(f"  - [yellow]{filename}[/yellow]: {result}")
    console.print("="*78)

    # --- Optional: Cleanup ---
    # Consider adding cleanup for the temp_diffs directory
    # import shutil
    # try:
    #     shutil.rmtree(output_dir)
    #     console.print(f"[info]Cleaned up temporary directory: {output_dir}")
    # except Exception as e:
    #     console.print(f"[warning]Could not clean up temporary directory {output_dir}: {e}")

    return results


# Example usage (if you want to run this script directly)
if __name__ == "__main__":
    # Make sure an Ollama server is running and the model is available
    # List available models via `ollama list` in your terminal
    DEFAULT_MODEL = "llama3:latest"  # Or choose another model like "mistral", "codellama", etc.

    console.print(f"[bold magenta]Starting Git Diff Analysis Tool[/bold magenta]")
    console.print(f"Using Ollama base URL: [blue]{BASE_URL}[/blue]")
    console.print(f"Using Model: [blue]{DEFAULT_MODEL}[/blue]\n")


    # --- Configuration ---
    target_commit = None # Analyze uncommitted changes (HEAD vs working directory)
    # target_commit = "HEAD~1" # Analyze the previous commit
    # target_commit = "your_specific_commit_hash" # Analyze a specific commit

    temp_directory = "temp_diffs_analysis" # Directory for diff files

    # --- Run Analysis ---
    analysis_results = analyze_git_changes(
        model_name=DEFAULT_MODEL,
        commit_hash=target_commit,
        output_dir=temp_directory,
        # system_prompt="You are an expert programmer reviewing code changes." # Optional custom prompt
    )

    # --- Display Results (Optional detailed view) ---
    # The analyze_git_changes function already prints a summary.
    # You could add more detailed output here if desired.
    # console.print("\n[bold underline]Detailed Analysis Results:[/bold underline]")
    # for filename, analysis in analysis_results:
    #     if not analysis.startswith("Error:"):
    #         console.print(Panel(f"[bold green]File:[/bold green] {filename}\n\n[bold cyan]Analysis:[/bold cyan]\n{analysis}",
    #                           title="Analysis Result", expand=False, border_style="blue"))
    #     else:
    #          console.print(Panel(f"[bold red]File:[/bold red] {filename}\n\n[bold yellow]Error:[/bold yellow]\n{analysis}",
    #                           title="Analysis Error", expand=False, border_style="red"))

    console.print("\n[bold magenta]Analysis process finished.[/bold magenta]")