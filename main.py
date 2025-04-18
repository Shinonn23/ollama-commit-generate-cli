# Standard Library Imports
import sys
import argparse
import json  # Import json for config file handling
import os  # Import os for path handling and directory creation
from typing import Optional, Dict, Any  # Import types for clarity

# Third-Party Library Imports
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm  # Import Confirm for yes/no prompts
from rich import print as rprint  # Use rich.print for consistent styling
from rich.text import Text  # Import Text for styled strings

# Internal Module Imports (assuming these exist and work as intended)
from _engine.ollama import get_models, display_models, select_model
from _engine.git import get_latest_commit_hash, analyze_git_changes
from _data.ollama import SYSTEM_PROMPT  # Assuming SYSTEM_PROMPT is a string constant

# --- Configuration ---
# Define the path for the default model configuration file
DEFAULT_CONFIG_DIR = "_data"
DEFAULT_CONFIG_FILE = os.path.join(DEFAULT_CONFIG_DIR, "default.json")

# --- Initialize Rich Console ---
# Create a global console instance
console = Console()


# --- Configuration File Management Functions ---


def load_default_model() -> Optional[str]:
    """
    Loads the default Ollama model name from the configuration file.

    Returns:
        Optional[str]: The default model name string if found and readable,
                       otherwise returns None.
    """
    if not os.path.exists(DEFAULT_CONFIG_FILE):
        # rprint(f"[dim]Config file not found: {DEFAULT_CONFIG_FILE}[/dim]") # Optional: verbose log
        return None

    try:
        with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)
            model_name = config.get("default_ollama_model")
            if isinstance(model_name, str) and model_name:
                # rprint(f"[dim]Loaded default model from config: {model_name}[/dim]") # Optional: verbose log
                return model_name
            else:
                rprint(
                    f"[warning]Config file '{DEFAULT_CONFIG_FILE}' does not contain a valid 'default_ollama_model' key.[/warning]"
                )
                return None
    except json.JSONDecodeError:
        rprint(
            f"[error]Error decoding JSON from config file: {DEFAULT_CONFIG_FILE}. File might be corrupted.[/error]"
        )
        return None
    except Exception as e:
        rprint(
            f"[error]Unexpected error reading config file {DEFAULT_CONFIG_FILE}: {e}[/error]"
        )
        return None


def save_default_model(model_name: str) -> None:
    """
    Saves the given model name as the default in the configuration file.

    Args:
        model_name (str): The Ollama model name to save as default.
    """
    try:
        # Ensure the data directory exists
        os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)

        config_data = {"default_ollama_model": model_name}

        with open(DEFAULT_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)

        rprint(
            f"[bold green]✔[/bold green] Default model '[cyan]{model_name}[/cyan]' saved to [dim]{DEFAULT_CONFIG_FILE}[/dim]"
        )

    except Exception as e:
        rprint(
            f"[error]Error saving default model to config file {DEFAULT_CONFIG_FILE}: {e}[/error]"
        )


# --- Main Application Logic ---


def main() -> None:
    """
    Main function to parse arguments, guide user interaction, and initiate
    the Git diff analysis using Ollama. Includes logic for managing
    a default Ollama model.
    """
    # --- 1. Argument Parsing ---
    # Create a rich panel for the description
    description_panel = Panel.fit(
        "[bold blue]Analyze Git Changes with Ollama LLMs[/bold blue]\n"
        "Export git diffs and send them to an Ollama model for analysis.",
        title="[bold green]Description[/bold green]",
        border_style="green",
    )
    
    # Create a plain text description for the argparse (Rich formatting won't work in argparse)
    description_str = "Analyze Git Changes with Ollama LLMs\nExport git diffs and send them to an Ollama model for analysis."
    
    parser = argparse.ArgumentParser(
        description=description_str
    )
    
    # Display the rich panel separately (this will show in the console but not affect argparse)
    console.print(description_panel)
    parser.add_argument(
        "-m",
        "--model",
        help="Specify Ollama model name to use for this run. Overrides default.",
        type=str,
    )
    parser.add_argument(
        "-c",
        "--commit",
        help="Specific commit hash to analyze. Defaults to uncommitted changes if not provided.",
        type=str,
    )
    parser.add_argument(
        "--output",
        default="temp_diffs",
        help="Output directory to save temporary diff files. Default: '%(default)s'",
        type=str,
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Number of parallel worker threads for generating diff files. Default: %(default)s",
    )
    parser.add_argument(
        "--prompt",
        help="Custom system prompt for the LLM analysis. Overrides the default system prompt.",
        type=str,
    )
    # Add new argument to specifically set/change the default model
    parser.add_argument(
        "--set-default-model",
        action="store_true",
        help="Interactively select and save an Ollama model as the default.",
    )

    args = parser.parse_args()

    # --- 2. Welcome Header ---
    rprint(
        Panel.fit(
            "[bold magenta]Git Diff Analyzer with Ollama[/bold magenta]\n"
            "[cyan]Tool for analyzing git changes using LLMs",
            title="[bold green]Welcome[/bold green]",
            border_style="green",
        )
    )
    rprint("")  # Add a blank line for spacing

    # --- 3. Ollama Model Management (Select/Set Default) ---
    rprint("[bold]Checking available Ollama models...[/bold]")
    models = get_models()  # Call the imported function

    if not models:
        rprint(
            Panel(
                "[bold red]Error:[/bold red] No Ollama models found.\n"
                "[yellow]Please ensure Ollama is running and models are downloaded.[/yellow]",
                title="[bold red]Ollama Connection Error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)  # Exit if no models are available

    # If the user specifically requested to set the default model
    if args.set_default_model:
        rprint(Panel("[bold blue]⚙️ Set Default Ollama Model[/bold blue]", expand=False))
        display_models(models)  # Show available models
        rprint("\nPlease select a model to set as default:")
        selected_model_for_default = select_model(models)  # Interactively select

        if selected_model_for_default:
            save_default_model(selected_model_for_default)  # Save the selection
            rprint(
                "\n[bold green]Configuration complete. You can now run the analyzer without specifying a model.[/bold green]"
            )
            sys.exit(0)  # Exit after setting the default
        else:
            rprint("\n[yellow]No model selected. Default model not changed.[/yellow]")
            sys.exit(1)  # Exit indicating no model was selected

    # If not setting default, proceed with analysis flow

    # Determine the model to use for this analysis run
    selected_model_for_analysis: Optional[str] = None

    if args.model:
        # User specified model via command line - prioritize this
        selected_model_for_analysis = args.model
        rprint(
            f"[info]Using model specified via command line: [cyan]{selected_model_for_analysis}[/cyan][/info]"
        )
        # Optional: Validate if the specified model exists in the available list
        # if not any(m['name'] == selected_model_for_analysis for m in models):
        #     rprint(f"[error]Specified model '{selected_model_for_analysis}' not found among available models.[/error]")
        #     selected_model_for_analysis = None # Force interactive selection or default loading

    if selected_model_for_analysis is None:
        # No model specified via command line, try loading default
        default_model_name = load_default_model()

        if default_model_name:
            # Check if the loaded default model is actually available
            if any(m["name"] == default_model_name for m in models):
                selected_model_for_analysis = default_model_name
                rprint(
                    f"[info]Using default model from [dim]{DEFAULT_CONFIG_FILE}[/dim]: [cyan]{selected_model_for_analysis}[/cyan][/info]"
                )
            else:
                rprint(
                    f"[warning]Default model '[yellow]{default_model_name}[/yellow]' not found among available models. It might have been removed.[/warning]"
                )
                rprint("[info]Falling back to interactive model selection.[/info]")

        if selected_model_for_analysis is None:
            # If still no model (no cmd line arg, no valid default) - prompt user
            rprint(
                "\n[bold blue]📦 Select an Ollama Model for this analysis[/bold blue]"
            )
            display_models(models)  # Show models again before prompting
            selected_model_for_analysis = select_model(models)  # Interactively select

            if selected_model_for_analysis:
                # Ask if they want to save this newly selected model as default
                save_as_default = Confirm.ask(
                    f"\n[bold cyan]Would you like to save '[cyan]{selected_model_for_analysis}[/cyan]' as the default model for future runs?[/bold cyan]",
                    default=True,  # Suggest saving as default
                )
                if save_as_default:
                    save_default_model(selected_model_for_analysis)
            else:
                rprint("\n[yellow]No model selected for analysis. Exiting.[/yellow]")
                return  # Exit if model selection was cancelled/failed

    # Final check before proceeding
    if not selected_model_for_analysis:
        # This case should ideally be caught by the checks above, but as a safeguard
        rprint(
            "[bold red]Fatal Error:[/bold red] No Ollama model could be determined for analysis. Exiting."
        )
        sys.exit(1)

    rprint(
        f"\n[bold green]✅ Proceeding with analysis using model:[/bold green] [cyan]{selected_model_for_analysis}[/cyan]"
    )

    # --- 4. Git Analysis Target Selection ---
    target_commit_hash: Optional[str] = args.commit

    if not target_commit_hash:
        rprint("\n[bold blue]🔍 Choose Analysis Target[/bold blue]")
        # Prompt user to choose between uncommitted changes and a specific commit
        choice = Prompt.ask(
            Text.from_markup(
                "[bold cyan]Analyze:[/bold cyan] (1) Current uncommitted changes or (2) Specific commit?"
            ),  # Use Text.from_markup for richer prompt
            choices=["1", "2"],
            default="1",
            show_choices=True,
        )

        if choice == "2":
            latest_commit = get_latest_commit_hash()  # Call the imported function
            if latest_commit:
                rprint(
                    f"[info]Latest commit hash: [yellow]{latest_commit[:8]}...[/yellow][/info]"
                )
            else:
                rprint("[warning]Could not retrieve latest commit hash.[/warning]")

            # Prompt for specific commit hash, offering latest as default if available
            target_commit_hash = Prompt.ask(
                "[bold cyan]Enter commit hash to analyze[/bold cyan]",
                default=latest_commit if latest_commit else None,
            )
            if not target_commit_hash:
                rprint(
                    "\n[yellow]No commit hash provided for analysis. Exiting.[/yellow]"
                )
                return  # Exit if user doesn't provide a commit hash

    analysis_target_desc = (
        f"commit [yellow]{target_commit_hash[:8]}...[/yellow]"
        if target_commit_hash
        else "[yellow]current uncommitted changes[/yellow]"
    )
    rprint(f"\n[info]Analysis target set to: {analysis_target_desc}[/info]")

    # --- 5. System Prompt Configuration ---
    system_prompt_to_use: str = (
        args.prompt if args.prompt is not None else SYSTEM_PROMPT
    )

    if args.prompt:
        rprint("[info]Using custom system prompt.[/info]")

    # --- 6. Initiate Analysis ---
    rprint(
        f"\n[bold blue]🧠 Starting Analysis with {selected_model_for_analysis}[/bold blue]"
    )
    rprint("-" * 80)  # Separator

    # Call the imported analysis function
    analyze_git_changes(
        model_name=selected_model_for_analysis,  # Use the determined model name
        commit_hash=target_commit_hash,
        output_dir=args.output,
        system_prompt=system_prompt_to_use,
        
    )

    rprint("-" * 80)  # Separator
    rprint("\n[bold green]✅ Analysis process complete![/bold green]")
    rprint("[blue]Thank you for using the Git Diff Analyzer.[/blue]")


# --- Entry Point ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        rprint("\n[bold yellow]✋ Operation cancelled by user.[/bold yellow]")
        sys.exit(0)  # Exit cleanly
    except Exception as e:
        # Catch any other unexpected exceptions
        rprint(
            Panel(
                f"[bold red]An unexpected error occurred:[/bold red]\n[yellow]{str(e)}[/yellow]",
                title="[bold red]Fatal Error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)  # Exit with an error code
