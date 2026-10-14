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
