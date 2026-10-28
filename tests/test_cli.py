"""Tests for CLI commands."""

from pathlib import Path
from typer.testing import CliRunner

from vissho.cli import app

runner = CliRunner()


def test_init_creates_config(tmp_path: Path) -> None:
    """Test vissho init creates config.yaml at target location."""
    target = tmp_path / "config.yaml"
    result = runner.invoke(app, ["init", "--output", str(target)])

    assert result.exit_code == 0
    assert target.exists()
    assert "Successfully initialized" in result.stdout
    content = target.read_text(encoding="utf-8")
    assert "prerequisites:" in content
    assert "columns:" in content


def test_init_fails_if_exists_without_force(tmp_path: Path) -> None:
    """Test vissho init refuses to overwrite without --force."""
    target = tmp_path / "config.yaml"
    target.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["init", "--output", str(target)])
    assert result.exit_code == 1
    assert "already exists" in result.stdout
    assert target.read_text(encoding="utf-8") == "existing content"


def test_init_overwrites_with_force(tmp_path: Path) -> None:
    """Test vissho init overwrites existing file when --force is given."""
    target = tmp_path / "config.yaml"
    target.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["init", "--output", str(target), "--force"])
    assert result.exit_code == 0
    content = target.read_text(encoding="utf-8")
    assert "prerequisites:" in content


def test_analyze_fails_when_config_missing(tmp_path: Path) -> None:
    """Test vissho analyze fails gracefully when config.yaml is not found."""
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    result = runner.invoke(
        app,
        ["analyze", str(slides_dir), "-c", str(tmp_path / "non_existent.yaml")],
    )
    assert result.exit_code == 1
    assert "Configuration file" in result.stdout


def test_analyze_fails_when_slides_empty(tmp_path: Path) -> None:
    """Test vissho analyze fails when no slide images are found."""
    config_file = tmp_path / "config.yaml"
    runner.invoke(app, ["init", "-o", str(config_file)])

    empty_slides_dir = tmp_path / "slides"
    empty_slides_dir.mkdir()

    result = runner.invoke(
        app,
        ["analyze", str(empty_slides_dir), "-c", str(config_file)],
    )
    assert result.exit_code == 1
    assert "Slide discovery error" in result.stdout


def test_analyze_success(tmp_path: Path) -> None:
    """Test vissho analyze runs successfully with mocked analysis."""
    from unittest.mock import patch
    from PIL import Image
    from vissho.llm.client import SlideAnalysisOutput
    from vissho.pipeline.phase1_analyze import SlideAnalyzer, SlideAnalysisResult

    config_file = tmp_path / "config.yaml"
    runner.invoke(app, ["init", "-o", str(config_file)])

    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    img = Image.new("RGB", (10, 10), color="red")
    img.save(slides_dir / "slide_01.png", format="PNG")

    dummy_result = SlideAnalysisResult(
        slide_number=1,
        image_path=str((slides_dir / "slide_01.png").resolve()),
        image_hash="dummyhash",
        analysis=SlideAnalysisOutput(
            title="イントロダクション",
            topics=["ガイダンス"],
            key_points=["講義概要"],
            suggested_activities=["講義"],
            estimated_minutes=15,
            instructor_notes=[],
        ),
        supplementary_notes=[],
        cached=False,
    )

    with patch.object(
        SlideAnalyzer,
        "analyze_slide",
        return_value=dummy_result,
    ) as mock_analyze:
        result = runner.invoke(
            app,
            ["analyze", str(slides_dir), "-c", str(config_file)],
        )

        assert result.exit_code == 0
        assert "Slide Analysis Results (Phase 1)" in result.stdout
        assert "イントロダクション" in result.stdout
        assert "Analysis complete: 1 slides" in result.stdout
        mock_analyze.assert_called_once()


def test_analyze_with_export_options(tmp_path: Path) -> None:
    """Test vissho analyze with --excel, --markdown, and -o options."""
    from unittest.mock import patch
    from PIL import Image
    from vissho.llm.client import SlideAnalysisOutput
    from vissho.pipeline.phase1_analyze import SlideAnalyzer, SlideAnalysisResult

    config_file = tmp_path / "config.yaml"
    runner.invoke(app, ["init", "-o", str(config_file)])

    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(slides_dir / "slide_01.png", format="PNG")

    dummy_result = SlideAnalysisResult(
        slide_number=1,
        image_path=str((slides_dir / "slide_01.png").resolve()),
        image_hash="dummyhash",
        analysis=SlideAnalysisOutput(
            title="テストスライド",
            topics=["トピック1"],
            key_points=["要点1"],
            suggested_activities=["解説"],
            estimated_minutes=20,
            instructor_notes=[],
        ),
        supplementary_notes=[],
        cached=False,
    )

    excel_out = tmp_path / "slides.xlsx"
    md_out = tmp_path / "slides.md"
    json_out = tmp_path / "slides.json"

    with patch.object(SlideAnalyzer, "analyze_slide", return_value=dummy_result):
        result = runner.invoke(
            app,
            [
                "analyze",
                str(slides_dir),
                "-c",
                str(config_file),
                "-x",
                str(excel_out),
                "--md",
                str(md_out),
                "-o",
                str(json_out),
            ],
        )

        assert result.exit_code == 0
        assert excel_out.exists()
        assert md_out.exists()
        assert json_out.exists()
        assert "Saved slide analyses Excel workbook to:" in result.stdout
        assert "Saved slide analyses Markdown to:" in result.stdout
        assert "Saved slide analyses JSON to:" in result.stdout


def test_preview_slide_analyses(tmp_path: Path) -> None:
    """Test vissho preview with slide analysis JSON."""
    import json

    slides_json = tmp_path / "slides.json"
    dummy_data = [
        {
            "slide_number": 1,
            "image_path": "slide_01.png",
            "image_hash": "hash1",
            "analysis": {
                "title": "スライドタイトル",
                "topics": ["トピックA"],
                "key_points": ["ポイントA"],
                "suggested_activities": ["演習"],
                "estimated_minutes": 30,
                "instructor_notes": [],
            },
            "supplementary_notes": [],
            "cached": True,
        }
    ]
    slides_json.write_text(json.dumps(dummy_data, ensure_ascii=False), encoding="utf-8")

    # Preview in terminal
    res_term = runner.invoke(app, ["preview", str(slides_json)])
    assert res_term.exit_code == 0
    assert "Slide Analysis Results (Phase 1)" in res_term.stdout
    assert "スライドタイトル" in res_term.stdout

    # Export to Excel from preview
    out_xlsx = tmp_path / "preview_slides.xlsx"
    res_excel = runner.invoke(app, ["preview", str(slides_json), "-f", "excel", "-o", str(out_xlsx)])
    assert res_excel.exit_code == 0
    assert out_xlsx.exists()



def test_map_command_success(tmp_path: Path) -> None:
    """Test vissho map runs successfully and outputs curriculum plan table and JSON."""
    from unittest.mock import patch
    from PIL import Image
    from vissho.llm.client import SlideAnalysisOutput
    from vissho.pipeline.phase1_analyze import SlideAnalysisResult, SlideAnalyzer
    from vissho.pipeline.phase2_map import SessionMapper
    from vissho.core.schema import create_curriculum_plan_model
    from vissho.config import load_config

    config_file = tmp_path / "config.yaml"
    runner.invoke(app, ["init", "-o", str(config_file)])
    cfg = load_config(config_file)

    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(slides_dir / "slide_01.png", format="PNG")

    dummy_analysis = SlideAnalysisResult(
        slide_number=1,
        image_path=str((slides_dir / "slide_01.png").resolve()),
        image_hash="dummyhash",
        analysis=SlideAnalysisOutput(
            title="概要",
            topics=["Web"],
            key_points=["基礎"],
            suggested_activities=["講義"],
            estimated_minutes=90,
            instructor_notes=[],
        ),
        supplementary_notes=[],
        cached=False,
    )

    curriculum_cls = create_curriculum_plan_model(cfg.columns)
    dummy_plan = curriculum_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "Web基礎入門",
                    "rows": [
                        {
                            "session_number": "第1コマ",
                            "topic": "Webの基礎",
                            "learning_objectives": "Webの仕組みを説明できる",
                            "activities": "スライド講義",
                            "allocated_minutes": 90,
                            "remarks": "PC環境を事前に確認する",
                            "source_slides": [1],
                        }
                    ],
                    "total_minutes": 90,
                }
            ],
            "unassigned_slides": [],
        }
    )

    output_json = tmp_path / "plan.json"

    with patch.object(
        SlideAnalyzer, "analyze_slide", return_value=dummy_analysis
    ), patch.object(SessionMapper, "map_sessions", return_value=dummy_plan):
        result = runner.invoke(
            app,
            [
                "map",
                str(slides_dir),
                "-c",
                str(config_file),
                "-o",
                str(output_json),
            ],
        )

        assert result.exit_code == 0
        assert "第1コマ: Web基礎入門" in result.stdout
        assert "Webの基" in result.stdout
        assert output_json.exists()
        content = output_json.read_text(encoding="utf-8")
        assert "Webの基礎" in content
        assert "Web基礎入門" in content


def test_run_command_success(tmp_path: Path) -> None:
    """Test vissho run executes end-to-end pipeline and displays validation summary."""
    from unittest.mock import patch
    from PIL import Image
    from vissho.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
    from vissho.core.schema import create_curriculum_plan_model
    from vissho.core.validator import ValidationReport, SessionValidation
    from vissho.config import load_config

    config_file = tmp_path / "config.yaml"
    runner.invoke(app, ["init", "-o", str(config_file)])
    cfg = load_config(config_file)

    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(slides_dir / "slide_01.png", format="PNG")

    curriculum_cls = create_curriculum_plan_model(cfg.columns)
    dummy_plan = curriculum_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "Web基礎入門 (完成版)",
                    "rows": [
                        {
                            "session_number": "第1コマ",
                            "topic": "Webの基礎",
                            "learning_objectives": "Webの仕組みを説明できる",
                            "activities": "スライド講義",
                            "allocated_minutes": 90,
                            "remarks": "事前準備完了",
                            "source_slides": [1],
                        }
                    ],
                    "total_minutes": 90,
                }
            ],
            "unassigned_slides": [],
        }
    )

    dummy_report = ValidationReport(
        is_valid=True,
        total_sessions_valid=True,
        total_sessions_actual=1,
        total_sessions_target=1,
        total_minutes_actual=90,
        total_minutes_target=90,
        total_minutes_difference=0,
        session_validations=[
            SessionValidation(
                session_number=1,
                session_title="Web基礎入門 (完成版)",
                allocated_minutes=90,
                target_minutes=90,
                difference=0,
                is_valid=True,
            )
        ],
        referenced_slides=[1],
        unassigned_slides=[],
        missing_slides=[],
        invalid_slide_references=[],
        errors=[],
        warnings=[],
    )

    dummy_pipeline_result = PipelineResult(
        slide_analyses=[],
        initial_plan=dummy_plan,
        final_plan=dummy_plan,
        validation_report=dummy_report,
        refined=False,
    )

    output_json = tmp_path / "final_plan.json"

    with patch.object(
        PipelineOrchestrator, "run", return_value=dummy_pipeline_result
    ):
        result = runner.invoke(
            app,
            [
                "run",
                str(slides_dir),
                "-c",
                str(config_file),
                "-o",
                str(output_json),
            ],
        )

        assert result.exit_code == 0
        assert "Starting vissho 3-phase instruction plan pipeline" in result.stdout
        assert "Web基礎入門 (完成版)" in result.stdout
        assert "Validation Status: PASSED" in result.stdout
        assert output_json.exists()
        content = output_json.read_text(encoding="utf-8")
        assert "Web基礎入門 (完成版)" in content


def test_run_with_exporter_options(tmp_path: Path) -> None:
    """Test vissho run with --excel, --markdown, and extension-based --output."""
    import json
    from unittest.mock import patch
    from PIL import Image
    from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig
    from vissho.core.schema import create_curriculum_plan_model
    from vissho.core.validator import ValidationReport
    from vissho.pipeline.orchestrator import PipelineOrchestrator, PipelineResult

    config_file = tmp_path / "config.yaml"
    cfg = VisshoConfig(
        prerequisites=Prerequisites(
            purpose="テスト講座",
            target_audience="専門生",
            total_sessions=1,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号", width=12),
            ColumnDefinition(name="topic", description="単元", width=25),
            ColumnDefinition(name="allocated_minutes", description="配当時間", width=14),
        ],
    )
    with config_file.open("w", encoding="utf-8") as f:
        import yaml

        yaml.safe_dump(cfg.model_dump(), f)

    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    img_path = slides_dir / "slide_01.png"
    Image.new("RGB", (100, 100), color="white").save(img_path)

    plan_cls = create_curriculum_plan_model(cfg.columns)
    dummy_plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマ",
                    "rows": [
                        {
                            "session_number": "第1コマ",
                            "topic": "Python入門",
                            "allocated_minutes": 90,
                        }
                    ],
                    "total_minutes": 90,
                }
            ],
            "unassigned_slides": [],
        }
    )

    dummy_report = ValidationReport(
        is_valid=True,
        total_sessions_valid=True,
        total_sessions_actual=1,
        total_sessions_target=1,
        total_minutes_actual=90,
        total_minutes_target=90,
        total_minutes_difference=0,
        session_validations=[],
        referenced_slides=[1],
        unassigned_slides=[],
        missing_slides=[],
        invalid_slide_references=[],
        errors=[],
        warnings=[],
    )

    dummy_pipeline_result = PipelineResult(
        slide_analyses=[],
        initial_plan=dummy_plan,
        final_plan=dummy_plan,
        validation_report=dummy_report,
        refined=False,
    )

    excel_file = tmp_path / "exported.xlsx"
    md_file = tmp_path / "exported.md"

    with patch.object(PipelineOrchestrator, "run", return_value=dummy_pipeline_result):
        result = runner.invoke(
            app,
            [
                "run",
                str(slides_dir),
                "-c",
                str(config_file),
                "-x",
                str(excel_file),
                "--md",
                str(md_file),
            ],
        )

        assert result.exit_code == 0
        assert excel_file.exists()
        assert md_file.exists()
        assert "Saved Excel workbook to:" in result.stdout
        assert "Saved Markdown to:" in result.stdout


def test_preview_command(tmp_path: Path) -> None:
    """Test vissho preview in terminal, markdown, excel, and json formats."""
    import json
    import yaml
    from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig

    config_file = tmp_path / "config.yaml"
    cfg = VisshoConfig(
        prerequisites=Prerequisites(
            purpose="プレビューテスト講座",
            target_audience="専門生",
            total_sessions=1,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号", width=12),
            ColumnDefinition(name="topic", description="単元", width=25),
            ColumnDefinition(name="allocated_minutes", description="配当時間", width=14),
        ],
    )
    with config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg.model_dump(), f)

    plan_json = tmp_path / "plan.json"
    plan_data = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "プレビュー単元",
                "rows": [
                    {
                        "session_number": "第1コマ",
                        "topic": "基礎",
                        "allocated_minutes": 90,
                    }
                ],
                "total_minutes": 90,
            }
        ],
        "unassigned_slides": [],
    }
    with plan_json.open("w", encoding="utf-8") as f:
        json.dump(plan_data, f)

    # 1. Terminal preview
    res_term = runner.invoke(app, ["preview", str(plan_json), "-c", str(config_file)])
    assert res_term.exit_code == 0
    assert "プレビュー単元" in res_term.stdout
    assert "Validation Status: PASSED" in res_term.stdout

    # 2. Markdown export preview
    md_out = tmp_path / "preview.md"
    res_md = runner.invoke(
        app,
        ["preview", str(plan_json), "-c", str(config_file), "-f", "markdown", "-o", str(md_out)],
    )
    assert res_md.exit_code == 0
    assert md_out.exists()
    assert "# 学習指導案: プレビューテスト講座" in md_out.read_text(encoding="utf-8")

    # 3. Excel export preview
    xlsx_out = tmp_path / "preview.xlsx"
    res_xlsx = runner.invoke(
        app,
        ["preview", str(plan_json), "-c", str(config_file), "-f", "excel", "-o", str(xlsx_out)],
    )
    assert res_xlsx.exit_code == 0
    assert xlsx_out.exists()

    # 4. JSON export preview
    json_out = tmp_path / "preview_meta.json"
    res_json = runner.invoke(
        app,
        ["preview", str(plan_json), "-c", str(config_file), "-f", "json", "-o", str(json_out)],
    )
    assert res_json.exit_code == 0
    assert json_out.exists()
    meta_loaded = json.loads(json_out.read_text(encoding="utf-8"))
    assert meta_loaded["version"] == "1.0"
    assert "prerequisites" in meta_loaded

    # 5. Missing file error
    res_err = runner.invoke(app, ["preview", str(tmp_path / "non_existent.json")])
    assert res_err.exit_code == 1
    assert "not" in res_err.stdout and "found" in res_err.stdout



