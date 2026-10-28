"""Tests for Phase 2 SessionMapper."""

from typing import Any
import pytest
from pydantic import BaseModel

from vissho.config import (
    ColumnDefinition,
    Prerequisites,
    SupplementaryNote,
    VisshoConfig,
)
from vissho.llm.client import SlideAnalysisOutput
from vissho.pipeline.phase1_analyze import SlideAnalysisResult
from vissho.pipeline.phase2_map import SessionMapper


class FakeMappingClient:
    """Fake LLM client supporting 2-step structured mapping calls."""

    def __init__(
        self,
        outline_response: dict[str, Any] | None = None,
        session_responses: list[dict[str, Any]] | None = None,
    ) -> None:
        self.outline_response = outline_response or {
            "sessions": [
                {"session_number": 1, "session_title": "Web開発の基礎", "slide_numbers": [1]},
                {"session_number": 2, "session_title": "HTML基本演習", "slide_numbers": [2]},
            ],
            "unassigned_slides": [],
        }
        self.session_responses = session_responses or []
        self.prompts: list[str] = []
        self.call_count: int = 0

    @property
    def last_prompt(self) -> str:
        return self.prompts[-1] if self.prompts else ""

    def analyze_slide(self, image_path: Any, prompt: str, model: Any = None) -> Any:
        raise NotImplementedError

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any],
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.call_count += 1
        self.prompts.append(prompt)

        # Check if schema is CourseOutline (Step 2-A)
        schema_name = getattr(schema, "__name__", "")
        if schema_name == "CourseOutline" or "slide_numbers" in str(schema):
            return self.outline_response

        # Step 2-B session responses (call_count >= 2)
        sess_idx = self.call_count - 2
        if 0 <= sess_idx < len(self.session_responses):
            return self.session_responses[sess_idx]
        if self.session_responses:
            return self.session_responses[-1]

        # Default fallback session response
        return {
            "session_number": sess_idx + 1,
            "session_title": f"第{sess_idx + 1}コマ",
            "rows": [
                {
                    "session_number": f"第{sess_idx + 1}コマ",
                    "topic": "学習項目",
                    "activities": "講義と演習",
                    "allocated_minutes": 90,
                    "source_slides": [sess_idx + 1],
                }
            ],
            "total_minutes": 90,
        }


@pytest.fixture
def sample_config() -> VisshoConfig:
    return VisshoConfig(
        prerequisites=Prerequisites(
            purpose="Web開発入門",
            target_audience="専門学校生",
            total_sessions=2,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号"),
            ColumnDefinition(name="topic", description="単元"),
            ColumnDefinition(name="activities", description="授業活動"),
            ColumnDefinition(name="allocated_minutes", description="配当時間"),
            ColumnDefinition(name="source_slides", description="出典スライド"),
        ],
        supplementary_notes=[
            SupplementaryNote(slide_number=2, note="演習時間を十分に確保する")
        ],
    )


@pytest.fixture
def sample_slide_analyses() -> list[SlideAnalysisResult]:
    return [
        SlideAnalysisResult(
            slide_number=1,
            image_path="/path/to/slide_01.png",
            image_hash="hash1",
            analysis=SlideAnalysisOutput(
                title="導入・開発環境",
                topics=["HTML", "ブラウザ"],
                key_points=["Webの仕組み"],
                suggested_activities=["講義"],
                estimated_minutes=45,
                instructor_notes=[],
            ),
        ),
        SlideAnalysisResult(
            slide_number=2,
            image_path="/path/to/slide_02.png",
            image_hash="hash2",
            analysis=SlideAnalysisOutput(
                title="タグの基本と演習",
                topics=["pタグ", "aタグ"],
                key_points=["要素と属性"],
                suggested_activities=["ハンズオン演習"],
                estimated_minutes=45,
                instructor_notes=["演習時間を十分に確保する"],
            ),
            supplementary_notes=["演習時間を十分に確保する"],
        ),
    ]


def test_session_mapper_success(
    sample_config: VisshoConfig,
    sample_slide_analyses: list[SlideAnalysisResult],
) -> None:
    outline = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "Web開発の基礎と環境構築",
                "slide_numbers": [1],
            },
            {
                "session_number": 2,
                "session_title": "HTML基本タグと演習",
                "slide_numbers": [2],
            },
        ],
        "unassigned_slides": [],
    }
    session_1 = {
        "session_number": 1,
        "session_title": "Web開発の基礎と環境構築",
        "rows": [
            {
                "session_number": "第1コマ",
                "topic": "Webの仕組みと基本",
                "activities": "スライドを用いた講義と概要説明",
                "allocated_minutes": 90,
                "source_slides": [1],
            }
        ],
        "total_minutes": 90,
    }
    session_2 = {
        "session_number": 2,
        "session_title": "HTML基本タグと演習",
        "rows": [
            {
                "session_number": "第2コマ",
                "topic": "HTML基本タグの記法",
                "activities": "エディタを用いたハンズオン作成演習",
                "allocated_minutes": 90,
                "source_slides": [2],
            }
        ],
        "total_minutes": 90,
    }

    client = FakeMappingClient(
        outline_response=outline,
        session_responses=[session_1, session_2],
    )
    mapper = SessionMapper(config=sample_config, client=client)

    result = mapper.map_sessions(sample_slide_analyses)

    # 1 outline call + 2 session detail calls = 3 calls
    assert client.call_count == 3
    # First prompt is course outline
    assert "Web開発入門" in client.prompts[0]
    assert "導入・開発環境" in client.prompts[0]
    # Subsequent prompts are session details
    assert "第1コマ" in client.prompts[1]
    assert "第2コマ" in client.prompts[2]

    sessions = getattr(result, "sessions")
    assert len(sessions) == 2
    assert sessions[0].session_number == 1
    assert sessions[0].session_title == "Web開発の基礎と環境構築"
    assert sessions[0].total_minutes == 90
    assert sessions[0].rows[0].topic == "Webの仕組みと基本"
    assert sessions[0].rows[0].source_slides == [1]

    assert sessions[1].session_number == 2
    assert sessions[1].session_title == "HTML基本タグと演習"
    assert sessions[1].total_minutes == 90
    assert sessions[1].rows[0].topic == "HTML基本タグの記法"
    assert sessions[1].rows[0].source_slides == [2]


def test_session_mapper_recalculates_total_minutes(
    sample_config: VisshoConfig,
    sample_slide_analyses: list[SlideAnalysisResult],
) -> None:
    # LLM returned total_minutes=0 by mistake in session detail
    session_with_zero = {
        "session_number": 1,
        "session_title": "Web入門",
        "rows": [
            {
                "session_number": "1",
                "topic": "導入",
                "activities": "解説",
                "allocated_minutes": 40,
                "source_slides": [1],
            },
            {
                "session_number": "1",
                "topic": "演習",
                "activities": "コーディング",
                "allocated_minutes": 50,
                "source_slides": [2],
            },
        ],
        "total_minutes": 0,
    }

    outline = {
        "sessions": [
            {"session_number": 1, "session_title": "Web入門", "slide_numbers": [1, 2]},
            {"session_number": 2, "session_title": "まとめ", "slide_numbers": []},
        ],
        "unassigned_slides": [],
    }

    client = FakeMappingClient(
        outline_response=outline,
        session_responses=[session_with_zero],
    )
    mapper = SessionMapper(config=sample_config, client=client)

    result = mapper.map_sessions(sample_slide_analyses)
    session_1 = getattr(result, "sessions")[0]
    # Automatically recalculated to 40 + 50 = 90
    assert session_1.total_minutes == 90


def test_session_mapper_empty_slides_raises(sample_config: VisshoConfig) -> None:
    client = FakeMappingClient({})
    mapper = SessionMapper(config=sample_config, client=client)

    with pytest.raises(ValueError, match="Cannot map empty slide analysis"):
        mapper.map_sessions([])


def test_session_mapper_with_unassigned_slides(
    sample_config: VisshoConfig,
    sample_slide_analyses: list[SlideAnalysisResult],
) -> None:
    outline = {
        "sessions": [
            {"session_number": 1, "session_title": "Web入門", "slide_numbers": [1]},
            {"session_number": 2, "session_title": "Web基礎", "slide_numbers": []},
        ],
        "unassigned_slides": [2],
    }

    client = FakeMappingClient(outline_response=outline)
    mapper = SessionMapper(config=sample_config, client=client)

    result = mapper.map_sessions(sample_slide_analyses)
    assert getattr(result, "unassigned_slides") == [2]


def test_session_mapper_progress_callback(
    sample_config: VisshoConfig,
    sample_slide_analyses: list[SlideAnalysisResult],
) -> None:
    client = FakeMappingClient()
    mapper = SessionMapper(config=sample_config, client=client)

    steps: list[tuple[int, int]] = []

    def on_progress(cur: int, tot: int) -> None:
        steps.append((cur, tot))

    mapper.map_sessions(sample_slide_analyses, progress_callback=on_progress)

    # total_sessions is 2
    assert steps == [(1, 2), (2, 2)]
