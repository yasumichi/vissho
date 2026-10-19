"""CLI entry point for vissho."""

from pathlib import Path
from typing import Annotated
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from vissho.config import DEFAULT_CONFIG_TEMPLATE, load_config
from vissho.llm.client import OllamaClient
from vissho.pipeline.phase1_analyze import SlideAnalysisResult, SlideAnalyzer
from vissho.utils.cache import SlideCache
from vissho.utils.image import find_slide_images

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


@app.command()
def analyze(
    slides_dir: Annotated[
        Path,
        typer.Argument(
            help="Directory containing slide images.",
        ),
    ],
    config_path: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to configuration file.",
        ),
    ] = Path("config.yaml"),
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Ollama vision model to use (default: qwen2.5-vl).",
        ),
    ] = None,
    pattern: Annotated[
        str,
        typer.Option(
            "--pattern",
            "-p",
            help="Glob pattern for slide image files.",
        ),
    ] = "*.png",
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache",
            help="Ignore existing cache and force re-analysis.",
        ),
    ] = False,
    cache_dir: Annotated[
        Path,
        typer.Option(
            "--cache-dir",
            help="Directory to store cache files.",
        ),
    ] = Path(".vissho_cache"),
) -> None:
    """Analyze individual slide images (Phase 1) and cache intermediate results."""
    # 1. Load configuration
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(
            f"[bold red]Error:[/bold red] Configuration file '{config_path}' not found. "
            f"Run [bold cyan]vissho init[/bold cyan] to generate a template."
        )
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # 2. Find slide images
    try:
        slide_items = find_slide_images(slides_dir, pattern=pattern)
    except Exception as e:
        console.print(f"[bold red]Slide discovery error:[/bold red] {e}")
        raise typer.Exit(code=1)

    total_slides = len(slide_items)
    console.print(
        f"[bold blue]Phase 1: Analyzing {total_slides} slides from[/bold blue] [cyan]{slides_dir}[/cyan]"
    )

    # 3. Setup analyzer
    client = OllamaClient(default_model=model)
    cache = SlideCache(cache_dir=cache_dir)
    analyzer = SlideAnalyzer(config=config, client=client, cache=cache, model=model)

    results: list[SlideAnalysisResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Analyzing slides...", total=total_slides)

        for num, path in slide_items:
            progress.update(
                task_id,
                description=f"Analyzing slide {num} ({path.name})...",
            )
            try:
                res = analyzer.analyze_slide(
                    slide_number=num,
                    image_path=path,
                    use_cache=not no_cache,
                )
                results.append(res)
            except Exception as e:
                progress.stop()
                console.print(
                    f"\n[bold red]Analysis failed on slide {num} ({path.name}):[/bold red] {e}"
                )
                raise typer.Exit(code=1)

            progress.advance(task_id)

    # 4. Display results summary table
    table = Table(
        title="Slide Analysis Results (Phase 1)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", style="bold", width=26)
    table.add_column("Topics", width=30)
    table.add_column("Est. (min)", justify="right", width=10)
    table.add_column("Notes", justify="right", width=6)
    table.add_column("Status", width=10)

    cached_count = 0
    total_est_minutes = 0

    for r in results:
        if r.cached:
            cached_count += 1
            status_text = "[green]Cached[/green]"
        else:
            status_text = "[cyan]Inferred[/cyan]"

        total_est_minutes += r.analysis.estimated_minutes
        topics_str = ", ".join(r.analysis.topics[:3])
        if len(r.analysis.topics) > 3:
            topics_str += "..."

        notes_count = str(len(r.supplementary_notes)) if r.supplementary_notes else "-"

        table.add_row(
            str(r.slide_number),
            r.analysis.title,
            topics_str,
            f"{r.analysis.estimated_minutes} min",
            notes_count,
            status_text,
        )

    console.print()
    console.print(table)
    console.print(
        f"\n[bold green]Analysis complete:[/bold green] {total_slides} slides "
        f"({cached_count} cached, {total_slides - cached_count} inferred) | "
        f"Total estimated duration: [bold]{total_est_minutes} minutes[/bold]"
    )


if __name__ == "__main__":
    app()
