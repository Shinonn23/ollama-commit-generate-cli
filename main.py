import sys
import requests
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
import subprocess

BASE_URL = "http://localhost:11434/api"

console = Console()


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


def ask_question(model_name, prompt) -> None:
    """Send a question to the model and display the answer"""
    data = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
    }

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold blue]Thinking ({model_name})..."),
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            response = requests.post(f"{BASE_URL}/generate", json=data)

        if response.status_code == 200:
            result = response.json()
            console.print(
                Panel(
                    Markdown(result.get("response", "No answer")),
                    title=f"[bold green]Answer from {model_name}",
                    border_style="green",
                )
            )
        else:
            console.print(f"[bold red]Error: {response.status_code}")
    except requests.exceptions.ConnectionError:
        console.print("[bold red]Unable to connect to Ollama server")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Ollama CLI Client")
    parser.add_argument("-m", "--model", help="Specify model name to use")
    parser.add_argument("-p", "--prompt", help="Specify question to ask")
    args = parser.parse_args()

    # Show header
    console.print(
        Panel.fit(
            "[bold magenta]Ollama CLI Client[/bold magenta]\n"
            "[cyan]Tool for managing and using AI models through Ollama API",
            title="[bold green]Welcome",
            border_style="green",
        )
    )

    # Get models and display them
    models = get_models()
    display_models(models)

    if not models:
        return

    # If model and prompt are specified via args
    if args.model and args.prompt:
        ask_question(args.model, args.prompt)
        return

    # Let user select a model
    selected_model = args.model or select_model(models)
    if not selected_model:
        console.print("[yellow]Thank you for using the service")
        return

    console.print(f"[bold green]Selected model: {selected_model}")

    # Let user input questions
    while True:
        prompt = args.prompt or console.input(
            "\n[bold yellow]Question (type 'q' to quit): "
        )

        if prompt.lower() == "q":
            # Stop model using direct command

            try:
                subprocess.run(["ollama", "stop", selected_model], check=True)
                console.print(
                    f"[bold yellow]Model {selected_model} stopped successfully"
                )
            except (subprocess.SubprocessError, FileNotFoundError):
                console.print("[bold red]Failed to stop the model")
            break

        if prompt:
            ask_question(selected_model, prompt)

        # If prompt was specified via args, run only once
        if args.prompt:
            break

    console.print("[bold green]Thank you for using the service!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Operation cancelled")
        sys.exit(0)
