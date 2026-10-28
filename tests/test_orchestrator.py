"""Tests for PipelineOrchestrator."""

from pathlib import Path
from typing import Any
import pytest
from PIL import Image
from pydantic import BaseModel

from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig
from vissho.llm.client import SlideAnalysisOutput
from vissho.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
from vissho.utils.cache import SlideCache


def _create_dummy_png(path: Path, color: str = "blue") -> None:
    img = Image.new("RGB", (32, 32), color=color)
    img.save(path, format="PNG")


class FakePipelineClient:
    """Mock LLM client capable of handling Phase 1 and Phase 2/3 structured calls."""

    def __init__(self) -> None:
        self.analyze_count = 0
        self.generate_count = 0

    def analyze_slide(
        self,
        image_path: Path,
        prompt: str,
        model: str | None = None,
    ) -> SlideAnalysisOutput:
        self.analyze_count += 1
        return SlideAnalysisOutput(
            title=f"Title for {image_path.name}",
            topics=["Topic"],
            key_points=["Point"],
            suggested_activities=["Activity"],
            estimated_minutes=90,
            instructor_notes=[],
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any],
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.generate_count += 1
        schema_name = getattr(schema, "__name__", "")
        if schema_name == "CourseOutline" or "slide_numbers" in str(schema):
            return {
                "sessions": [
                    {
                        "session_number": 1,
                        "session_title": "第1コマ: 総合学習",
                        "slide_numbers": [1],
                    }
                ],
                "unassigned_slides": [],
            }

        # Step 2-B: single session detail
        return {
            "session_number": 1,
            "session_title": "第1コマ: 総合学習",
            "rows": [
                {
                    "session_number": "第1コマ",
                    "topic": "総合学習",
                    "allocated_minutes": 90,
                    "source_slides": [1],
                }
            ],
            "total_minutes": 90,
        }


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


def test_orchestrator_end_to_end(tmp_path: Path, sample_config: VisshoConfig) -> None:
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    _create_dummy_png(slides_dir / "slide_01.png")

    fake_client = FakePipelineClient()
    cache = SlideCache(cache_dir=tmp_path / "cache")
    orchestrator = PipelineOrchestrator(
        config=sample_config,
        client=fake_client,
        cache=cache,
    )

    stage_events: list[str] = []

    def on_progress(stage: str, cur: int, tot: int) -> None:
        stage_events.append(stage)

    result = orchestrator.run(
        slides_dir=slides_dir,
        progress_callback=on_progress,
    )

    assert isinstance(result, PipelineResult)
    assert len(result.slide_analyses) == 1
    assert result.validation_report.is_valid is True
    assert fake_client.analyze_count == 1
    assert fake_client.generate_count == 2  # Phase 2 (outline + 1 session), Phase 3 skipped because valid
    assert "phase1_start" in stage_events
    assert "phase2_start" in stage_events
    assert "phase2_session" in stage_events
    assert "phase3_start" in stage_events
    assert "complete" in stage_events
