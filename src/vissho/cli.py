"""CLI entry point for vissho."""

from pathlib import Path
from typing import Annotated
import typer
from rich.console import Console

from vissho.config import DEFAULT_CONFIG_TEMPLATE

app = typer.Typer(
    name="vissho",
    help="Lesson instruction plan creation assistant powered by vision LLMs.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """vissho - Lesson instruction plan creation assistant."""
    pass


@app.command()
def init(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path to create the configuration file.",
        ),
    ] = Path("config.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing configuration file if it already exists.",
        ),
    ] = False,
) -> None:
    """Generate a template configuration file (config.yaml) in the current directory."""
    if output.exists() and not force:
        console.print(
            f"[bold red]Error:[/bold red] File '{output}' already exists. Use [bold yellow]--force[/bold yellow] to overwrite."
        )
        raise typer.Exit(code=1)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        f.write(DEFAULT_CONFIG_TEMPLATE)

    console.print(
        f"[bold green]Successfully initialized configuration file:[/bold green] [cyan]{output.resolve()}[/cyan]"
    )


if __name__ == "__main__":
    app()
