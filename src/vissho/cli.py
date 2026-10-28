"""CLI entry point for vissho."""

from pathlib import Path
from typing import Annotated, Any
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from vissho.config import DEFAULT_CONFIG_TEMPLATE, VisshoConfig, load_config
from vissho.core.validator import ValidationReport, validate_curriculum_plan
from vissho.exporter import (
    export_slide_analyses_to_excel,
    export_slide_analyses_to_json,
    export_slide_analyses_to_markdown,
    export_to_excel,
    export_to_json,
    export_to_markdown,
)
from vissho.llm.client import OllamaClient
from vissho.pipeline.orchestrator import PipelineOrchestrator
from vissho.pipeline.phase1_analyze import SlideAnalysisResult, SlideAnalyzer
from vissho.pipeline.phase2_map import SessionMapper
from vissho.pipeline.phase3_review import ConsistencyReviewer
from vissho.utils.cache import SlideCache
from vissho.utils.image import find_slide_images

app = typer.Typer(
    name="vissho",
    help="Lesson instruction plan creation assistant powered by vision LLMs.",
    no_args_is_help=True,
)
console = Console()


def _export_outputs(
    plan: Any,
    config: VisshoConfig,
    validation_report: ValidationReport | None = None,
    output: Path | None = None,
    excel: Path | None = None,
    markdown: Path | None = None,
) -> None:
    """Save plan in requested export formats."""
    # 1. Explicit --excel option
    if excel:
        export_to_excel(plan, config, output_path=excel, validation_report=validation_report)
        console.print(f"[bold green]Saved Excel workbook to:[/bold green] [cyan]{excel.resolve()}[/cyan]")

    # 2. Explicit --markdown option
    if markdown:
        export_to_markdown(plan, config, output_path=markdown, validation_report=validation_report)
        console.print(f"[bold green]Saved Markdown to:[/bold green] [cyan]{markdown.resolve()}[/cyan]")

    # 3. Handle --output option based on file extension
    if output:
        suffix = output.suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".xltx"):
            export_to_excel(plan, config, output_path=output, validation_report=validation_report)
            console.print(f"[bold green]Saved Excel workbook to:[/bold green] [cyan]{output.resolve()}[/cyan]")
        elif suffix in (".md", ".markdown"):
            export_to_markdown(plan, config, output_path=output, validation_report=validation_report)
            console.print(f"[bold green]Saved Markdown to:[/bold green] [cyan]{output.resolve()}[/cyan]")
        else:
            # Default to JSON
            export_to_json(
                plan,
                output_path=output,
                config=config,
                validation_report=validation_report,
                include_metadata=False,
            )
            console.print(f"[bold green]Saved JSON plan to:[/bold green] [cyan]{output.resolve()}[/cyan]")


def _export_slide_analyses_outputs(
    results: list[Any],
    output: Path | None = None,
    excel: Path | None = None,
    markdown: Path | None = None,
    title: str = "スライド解析結果一覧",
) -> None:
    """Save slide analysis results in requested export formats."""
    # 1. Explicit --excel option
    if excel:
        export_slide_analyses_to_excel(results, output_path=excel, title=title)
        console.print(
            f"[bold green]Saved slide analyses Excel workbook to:[/bold green] [cyan]{excel.resolve()}[/cyan]"
        )

    # 2. Explicit --markdown option
    if markdown:
        export_slide_analyses_to_markdown(results, output_path=markdown, title=title)
        console.print(
            f"[bold green]Saved slide analyses Markdown to:[/bold green] [cyan]{markdown.resolve()}[/cyan]"
        )

    # 3. Handle --output option based on file extension
    if output:
        suffix = output.suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".xltx"):
            export_slide_analyses_to_excel(results, output_path=output, title=title)
            console.print(
                f"[bold green]Saved slide analyses Excel workbook to:[/bold green] [cyan]{output.resolve()}[/cyan]"
            )
        elif suffix in (".md", ".markdown"):
            export_slide_analyses_to_markdown(results, output_path=output, title=title)
            console.print(
                f"[bold green]Saved slide analyses Markdown to:[/bold green] [cyan]{output.resolve()}[/cyan]"
            )
        else:
            export_slide_analyses_to_json(results, output_path=output)
            console.print(
                f"[bold green]Saved slide analyses JSON to:[/bold green] [cyan]{output.resolve()}[/cyan]"
            )


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
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to output file (.xlsx, .md, or .json determined by extension).",
        ),
    ] = None,
    excel: Annotated[
        Path | None,
        typer.Option(
            "--excel",
            "-x",
            help="Path to save slide analysis results as an Excel workbook (.xlsx).",
        ),
    ] = None,
    markdown: Annotated[
        Path | None,
        typer.Option(
            "--markdown",
            "--md",
            help="Path to save slide analysis results as a Markdown document (.md).",
        ),
    ] = None,
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

    # 5. Export slide analysis results if requested
    _export_slide_analyses_outputs(
        results=results,
        output=output,
        excel=excel,
        markdown=markdown,
        title=f"スライド解析結果: {config.prerequisites.purpose}",
    )


@app.command()
def map(
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
            help="Ollama model to use for mapping (default: qwen2.5-vl).",
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
    cache_dir: Annotated[
        Path,
        typer.Option(
            "--cache-dir",
            help="Directory to store cache files.",
        ),
    ] = Path(".vissho_cache"),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to save generated curriculum plan (JSON by default, or determined by extension).",
        ),
    ] = None,
    excel: Annotated[
        Path | None,
        typer.Option(
            "--excel",
            "-x",
            help="Path to export curriculum plan to Excel (.xlsx).",
        ),
    ] = None,
    markdown: Annotated[
        Path | None,
        typer.Option(
            "--markdown",
            "--md",
            help="Path to export curriculum plan to Markdown (.md).",
        ),
    ] = None,
) -> None:
    """Map analyzed slide elements into structured class sessions (Phase 2)."""
    # 1. Load config
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(
            f"[bold red]Error:[/bold red] Configuration file '{config_path}' not found."
        )
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # 2. Collect & analyze slides (Phase 1)
    try:
        slide_items = find_slide_images(slides_dir, pattern=pattern)
    except Exception as e:
        console.print(f"[bold red]Slide discovery error:[/bold red] {e}")
        raise typer.Exit(code=1)

    client = OllamaClient(default_model=model)
    cache = SlideCache(cache_dir=cache_dir)
    analyzer = SlideAnalyzer(config=config, client=client, cache=cache, model=model)

    console.print(f"[bold blue]Step 1: Preparing slide analyses for {len(slide_items)} slides...[/bold blue]")
    slide_analyses: list[SlideAnalysisResult] = []
    for num, path in slide_items:
        res = analyzer.analyze_slide(slide_number=num, image_path=path, use_cache=True)
        slide_analyses.append(res)

    # 3. Execute Phase 2 Session Mapping
    console.print(
        f"[bold blue]Step 2: Mapping {len(slide_analyses)} slides into "
        f"{config.prerequisites.total_sessions} sessions ({config.prerequisites.session_minutes} min/session)...[/bold blue]"
    )

    mapper = SessionMapper(config=config, client=client, model=model)
    try:
        with console.status("[bold cyan]Structuring curriculum plan with LLM...[/bold cyan]"):
            curriculum_plan = mapper.map_sessions(slide_analyses)
    except Exception as e:
        console.print(f"[bold red]Mapping failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    # 4. Display mapped sessions
    sessions = getattr(curriculum_plan, "sessions", [])
    for session in sessions:
        table = Table(
            title=f"第{session.session_number}コマ: {session.session_title} (合計 {session.total_minutes}分 / 目標 {config.prerequisites.session_minutes}分)",
            show_header=True,
            header_style="bold cyan",
        )
        # Determine column headers from config
        for col in config.columns:
            table.add_column(
                col.name,
                overflow="fold",
                style="bold" if col.name in ("topic", "learning_objectives") else None,
            )

        for row in getattr(session, "rows", []):
            row_data = []
            for col in config.columns:
                val = getattr(row, col.name, "")
                if isinstance(val, list):
                    val_str = ", ".join(str(x) for x in val)
                else:
                    val_str = str(val or "")
                row_data.append(val_str)
            table.add_row(*row_data)

        console.print()
        console.print(table)

    unassigned = getattr(curriculum_plan, "unassigned_slides", [])
    if unassigned:
        console.print(f"\n[yellow]Unassigned slides:[/yellow] {unassigned}")

    # 5. Save output if requested
    _export_outputs(
        plan=curriculum_plan,
        config=config,
        output=output,
        excel=excel,
        markdown=markdown,
    )


@app.command()
def run(
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
            help="Ollama model to use.",
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
    force_refine: Annotated[
        bool,
        typer.Option(
            "--force-refine",
            help="Force LLM refinement even if deterministic rules pass.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to save generated curriculum plan (JSON by default, or determined by extension).",
        ),
    ] = None,
    excel: Annotated[
        Path | None,
        typer.Option(
            "--excel",
            "-x",
            help="Path to export curriculum plan to Excel (.xlsx).",
        ),
    ] = None,
    markdown: Annotated[
        Path | None,
        typer.Option(
            "--markdown",
            "--md",
            help="Path to export curriculum plan to Markdown (.md).",
        ),
    ] = None,
) -> None:
    """Execute complete 3-phase pipeline: Analyze -> Map -> Review."""
    # 1. Load config
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(
            f"[bold red]Error:[/bold red] Configuration file '{config_path}' not found."
        )
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        raise typer.Exit(code=1)

    client = OllamaClient(default_model=model)
    cache = SlideCache(cache_dir=cache_dir)
    orchestrator = PipelineOrchestrator(
        config=config,
        client=client,
        cache=cache,
        model=model,
    )

    console.print("[bold blue]Starting vissho 3-phase instruction plan pipeline...[/bold blue]")

    with console.status("[bold cyan]Running pipeline stages...[/bold cyan]") as status:
        def on_progress(stage: str, cur: int, tot: int) -> None:
            if stage == "phase1_start":
                status.update(f"[bold cyan]Phase 1: Analyzing {tot} slides...[/bold cyan]")
            elif stage == "phase1_slide":
                status.update(f"[bold cyan]Phase 1: Analyzed slide {cur}/{tot}...[/bold cyan]")
            elif stage == "phase2_start":
                status.update("[bold cyan]Phase 2: Mapping outline and sessions...[/bold cyan]")
            elif stage == "phase2_session":
                status.update(f"[bold cyan]Phase 2: Generating session {cur}/{tot} details...[/bold cyan]")
            elif stage == "phase3_start":
                status.update("[bold cyan]Phase 3: Validating & refining curriculum plan...[/bold cyan]")

        try:
            result = orchestrator.run(
                slides_dir=slides_dir,
                pattern=pattern,
                use_cache=not no_cache,
                force_refine=force_refine,
                progress_callback=on_progress,
            )
        except Exception as e:
            console.print(f"[bold red]Pipeline failed:[/bold red] {e}")
            raise typer.Exit(code=1)

    # Display final plan
    final_plan = result.final_plan
    sessions = getattr(final_plan, "sessions", [])
    for session in sessions:
        table = Table(
            title=f"第{session.session_number}コマ: {session.session_title} (合計 {session.total_minutes}分 / 目標 {config.prerequisites.session_minutes}分)",
            show_header=True,
            header_style="bold green",
        )
        for col in config.columns:
            table.add_column(
                col.name,
                overflow="fold",
                style="bold" if col.name in ("topic", "learning_objectives") else None,
            )

        for row in getattr(session, "rows", []):
            row_data = []
            for col in config.columns:
                val = getattr(row, col.name, "")
                if isinstance(val, list):
                    val_str = ", ".join(str(x) for x in val)
                else:
                    val_str = str(val or "")
                row_data.append(val_str)
            table.add_row(*row_data)

        console.print()
        console.print(table)

    # Validation summary
    rep = result.validation_report
    console.print()
    if rep.is_valid:
        console.print("[bold green]Validation Status: PASSED[/bold green] (All session times and slide coverages match constraints)")
    else:
        console.print("[bold yellow]Validation Status: ISSUES DETECTED[/bold yellow]")
        for err in rep.errors:
            console.print(f"  [red]• {err}[/red]")
        for warn in rep.warnings:
            console.print(f"  [yellow]• {warn}[/yellow]")

    console.print(
        f"Sessions: {rep.total_sessions_actual}/{rep.total_sessions_target} | "
        f"Total Minutes: {rep.total_minutes_actual}/{rep.total_minutes_target} min | "
        f"Refined by LLM: {'Yes' if result.refined else 'No (deterministic rules passed)'}"
    )

    unassigned = getattr(final_plan, "unassigned_slides", [])
    if unassigned:
        console.print(f"[dim]Unassigned slides: {unassigned}[/dim]")

    # Save output if requested
    _export_outputs(
        plan=final_plan,
        config=config,
        validation_report=rep,
        output=output,
        excel=excel,
        markdown=markdown,
    )


@app.command()
def preview(
    plan_path: Annotated[
        Path,
        typer.Argument(
            help="Path to generated curriculum plan JSON file.",
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
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Preview/export format: 'terminal', 'markdown', 'excel', or 'json'.",
        ),
    ] = "terminal",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to export the previewed plan.",
        ),
    ] = None,
) -> None:
    """Preview or export a curriculum plan from a JSON file in terminal, Markdown, Excel, or JSON format."""
    import json

    # 1. Load curriculum plan JSON
    if not plan_path.exists():
        console.print(f"[bold red]Error:[/bold red] Plan file '{plan_path}' not found.")
        raise typer.Exit(code=1)

    try:
        with plan_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        console.print(f"[bold red]Failed to read plan JSON:[/bold red] {e}")
        raise typer.Exit(code=1)

    if isinstance(data, list) and (len(data) == 0 or "analysis" in data[0] or "slide_number" in data[0]):
        # Slide analyses preview & export
        fmt = format.lower()
        if fmt == "terminal":
            table = Table(title="Slide Analysis Results (Phase 1)", show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4, justify="right")
            table.add_column("Title", style="bold", width=26)
            table.add_column("Topics", width=30)
            table.add_column("Est. (min)", justify="right", width=10)
            table.add_column("Notes", justify="right", width=6)
            for item in data:
                ana = item.get("analysis", {})
                topics_str = ", ".join(ana.get("topics", [])[:3])
                notes = item.get("supplementary_notes", []) or ana.get("instructor_notes", [])
                table.add_row(
                    str(item.get("slide_number", "")),
                    ana.get("title", ""),
                    topics_str,
                    f"{ana.get('estimated_minutes', 0)} min",
                    str(len(notes)) if notes else "-",
                )
            console.print()
            console.print(table)
            if output:
                _export_slide_analyses_outputs(data, output=output)
        elif fmt in ("markdown", "md"):
            md_text = export_slide_analyses_to_markdown(data, output_path=output)
            if output:
                console.print(f"[bold green]Saved slide analyses Markdown to:[/bold green] [cyan]{output.resolve()}[/cyan]")
            else:
                console.print(md_text)
        elif fmt in ("excel", "xlsx"):
            target_out = output or plan_path.with_suffix(".xlsx")
            export_slide_analyses_to_excel(data, output_path=target_out)
            console.print(f"[bold green]Saved slide analyses Excel workbook to:[/bold green] [cyan]{target_out.resolve()}[/cyan]")
        elif fmt == "json":
            json_text = export_slide_analyses_to_json(data, output_path=output)
            if output:
                console.print(f"[bold green]Saved slide analyses JSON to:[/bold green] [cyan]{output.resolve()}[/cyan]")
            else:
                console.print_json(json_text)
        else:
            console.print(f"[bold red]Unknown format:[/bold red] '{format}'.")
            raise typer.Exit(code=1)
        return

    if isinstance(data, dict) and "plan" in data and isinstance(data["plan"], dict):
        plan_dict = data["plan"]
        val_data = data.get("validation")
        validation_report = ValidationReport.model_validate(val_data) if val_data else None
    else:
        plan_dict = data
        validation_report = None

    # 2. Load configuration
    try:
        config = load_config(config_path)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # 3. Deterministic validation if not loaded
    if validation_report is None:
        validation_report = validate_curriculum_plan(plan_dict, config)

    # 4. Handle requested format
    fmt = format.lower()
    if fmt == "terminal":
        # Rich table output
        sessions = plan_dict.get("sessions", [])
        for session in sessions:
            s_num = session.get("session_number", 1)
            s_title = session.get("session_title", "")
            s_total = session.get("total_minutes", 0)
            table = Table(
                title=f"第{s_num}コマ: {s_title} (合計 {s_total}分 / 目標 {config.prerequisites.session_minutes}分)",
                show_header=True,
                header_style="bold green",
            )
            for col in config.columns:
                table.add_column(
                    col.name,
                    overflow="fold",
                    style="bold" if col.name in ("topic", "learning_objectives") else None,
                )
            for row in session.get("rows", []):
                row_data = []
                for col in config.columns:
                    val = row.get(col.name, "")
                    if isinstance(val, list):
                        val_str = ", ".join(str(x) for x in val)
                    else:
                        val_str = str(val or "")
                    row_data.append(val_str)
                table.add_row(*row_data)

            console.print()
            console.print(table)

        # Validation status
        console.print()
        if validation_report.is_valid:
            console.print("[bold green]Validation Status: PASSED[/bold green]")
        else:
            console.print("[bold yellow]Validation Status: ISSUES DETECTED[/bold yellow]")
            for err in validation_report.errors:
                console.print(f"  [red]• {err}[/red]")
            for warn in validation_report.warnings:
                console.print(f"  [yellow]• {warn}[/yellow]")

        unassigned = plan_dict.get("unassigned_slides", [])
        if unassigned:
            console.print(f"[dim]Unassigned slides: {unassigned}[/dim]")

        if output:
            _export_outputs(plan_dict, config, validation_report, output=output)

    elif fmt in ("markdown", "md"):
        md_text = export_to_markdown(
            plan_dict,
            config,
            output_path=output,
            validation_report=validation_report,
        )
        if output:
            console.print(f"[bold green]Saved Markdown to:[/bold green] [cyan]{output.resolve()}[/cyan]")
        else:
            console.print(md_text)

    elif fmt in ("excel", "xlsx"):
        target_out = output or plan_path.with_suffix(".xlsx")
        export_to_excel(
            plan_dict,
            config,
            output_path=target_out,
            validation_report=validation_report,
        )
        console.print(f"[bold green]Saved Excel workbook to:[/bold green] [cyan]{target_out.resolve()}[/cyan]")

    elif fmt == "json":
        json_text = export_to_json(
            plan_dict,
            output_path=output,
            config=config,
            validation_report=validation_report,
            include_metadata=True,
        )
        if output:
            console.print(f"[bold green]Saved JSON to:[/bold green] [cyan]{output.resolve()}[/cyan]")
        else:
            console.print_json(json_text)

    else:
        console.print(
            f"[bold red]Unknown format:[/bold red] '{format}'. "
            "Choose from 'terminal', 'markdown', 'excel', or 'json'."
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
