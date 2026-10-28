"""Tests for JSON exporter."""

import json
from pathlib import Path
import pytest

from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig
from vissho.core.schema import create_curriculum_plan_model
from vissho.core.validator import validate_curriculum_plan
from vissho.exporter.json_export import export_to_json


@pytest.fixture
def sample_config() -> VisshoConfig:
    return VisshoConfig(
        prerequisites=Prerequisites(
            purpose="テスト講座",
            target_audience="受講生",
            total_sessions=1,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号"),
            ColumnDefinition(name="topic", description="単元"),
            ColumnDefinition(name="allocated_minutes", description="配当時間"),
            ColumnDefinition(name="source_slides", description="出典スライド"),
        ],
    )


@pytest.fixture
def sample_plan_data() -> dict:
    return {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "単元1",
                "rows": [
                    {
                        "session_number": "第1コマ",
                        "topic": "導入",
                        "allocated_minutes": 90,
                        "source_slides": [1],
                    }
                ],
                "total_minutes": 90,
            }
        ],
        "unassigned_slides": [],
    }


def test_export_to_json_raw(sample_plan_data: dict, tmp_path: Path) -> None:
    """Test raw plan JSON export without metadata wrapping."""
    target_file = tmp_path / "plan.json"
    result = export_to_json(sample_plan_data, output_path=target_file, include_metadata=False)

    assert target_file.exists()
    loaded = json.loads(result)
    assert "sessions" in loaded
    assert len(loaded["sessions"]) == 1
    assert loaded["sessions"][0]["session_title"] == "単元1"
    assert "version" not in loaded


def test_export_to_json_with_metadata(sample_config: VisshoConfig, sample_plan_data: dict, tmp_path: Path) -> None:
    """Test JSON export with metadata wrapping including prerequisites, columns, and validation."""
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    model_plan = plan_cls.model_validate(sample_plan_data)
    report = validate_curriculum_plan(model_plan, sample_config, all_slide_numbers=[1])

    target_file = tmp_path / "plan_meta.json"
    result = export_to_json(
        model_plan,
        output_path=target_file,
        config=sample_config,
        validation_report=report,
        include_metadata=True,
    )

    assert target_file.exists()
    loaded = json.loads(result)

    assert loaded["version"] == "1.0"
    assert "prerequisites" in loaded
    assert loaded["prerequisites"]["purpose"] == "テスト講座"
    assert "columns" in loaded
    assert len(loaded["columns"]) == 4
    assert "plan" in loaded
    assert "validation" in loaded
    assert loaded["validation"]["is_valid"] is True


def test_export_slide_analyses_to_json(tmp_path: Path) -> None:
    from vissho.exporter.json_export import export_slide_analyses_to_json
    from vissho.llm.client import SlideAnalysisOutput
    from vissho.pipeline.phase1_analyze import SlideAnalysisResult

    dummy_results = [
        SlideAnalysisResult(
            slide_number=1,
            image_path="/path/to/slide_01.png",
            image_hash="hash1",
            analysis=SlideAnalysisOutput(
                title="導入・環境構築",
                topics=["Python"],
                key_points=["Python概要"],
                suggested_activities=["講義"],
                estimated_minutes=30,
                instructor_notes=[],
            ),
        )
    ]

    target_file = tmp_path / "slides.json"
    result = export_slide_analyses_to_json(dummy_results, output_path=target_file)

    assert target_file.exists()
    loaded = json.loads(result)
    assert isinstance(loaded, list)
    assert len(loaded) == 1
    assert loaded[0]["slide_number"] == 1
    assert loaded[0]["analysis"]["title"] == "導入・環境構築"

