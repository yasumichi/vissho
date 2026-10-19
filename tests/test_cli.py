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

