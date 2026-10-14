"""Tests for configuration loading, saving, and validation."""

from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError

from vissho.config import (
    DEFAULT_CONFIG_TEMPLATE,
    ColumnDefinition,
    Prerequisites,
    RubricItem,
    SupplementaryNote,
    VisshoConfig,
    load_config,
    save_config,
)


def test_default_config_template_is_valid() -> None:
    """Ensure the default config template parses and validates cleanly."""
    data = yaml.safe_load(DEFAULT_CONFIG_TEMPLATE)
    config = VisshoConfig.model_validate(data)

    assert config.prerequisites.total_sessions == 4
    assert config.prerequisites.session_minutes == 90
    assert config.prerequisites.total_minutes == 360
    assert len(config.prerequisites.rubric) == 3
    assert len(config.columns) == 7
    assert len(config.supplementary_notes) == 2


def test_get_notes_for_slide() -> None:
    """Verify filtering of supplementary notes by slide number."""
    config = VisshoConfig(
        prerequisites=Prerequisites(
            purpose="Test Course",
            target_audience="Beginners",
            total_sessions=2,
            session_minutes=60,
        ),
        columns=[ColumnDefinition(name="topic", description="Topic")],
        supplementary_notes=[
            SupplementaryNote(slide_number=1, note="Note 1"),
            SupplementaryNote(slide_number=2, note="Note 2A"),
            SupplementaryNote(slide_number=2, note="Note 2B"),
        ],
    )

    assert config.get_notes_for_slide(1) == ["Note 1"]
    assert config.get_notes_for_slide(2) == ["Note 2A", "Note 2B"]
    assert config.get_notes_for_slide(3) == []


def test_load_and_save_config(tmp_path: Path) -> None:
    """Verify round-trip saving and loading of configuration."""
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")

    loaded = load_config(cfg_file)
    assert loaded.prerequisites.purpose.startswith("〇〇技術")

    out_file = tmp_path / "output_config.yaml"
    save_config(loaded, out_file)
    assert out_file.exists()

    reloaded = load_config(out_file)
    assert reloaded.prerequisites.total_sessions == loaded.prerequisites.total_sessions
    assert len(reloaded.columns) == len(loaded.columns)


def test_validation_errors() -> None:
    """Ensure invalid config data raises appropriate validation errors."""
    with pytest.raises(ValidationError):
        Prerequisites(
            purpose="Invalid Sessions",
            target_audience="Students",
            total_sessions=0,  # Must be gt=0
            session_minutes=90,
        )

    with pytest.raises(ValidationError):
        ColumnDefinition(name="   ", description="Empty name")
