from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
import requests
from rich.panel import Panel
from rich.table import Table
from _data.ollama import BASE_URL

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
