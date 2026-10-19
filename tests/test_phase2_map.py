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
    """Fake LLM client that returns predefined structured responses."""

    def __init__(self, response_data: dict[str, Any]) -> None:
        self.response_data = response_data
        self.last_prompt: str = ""
        self.call_count: int = 0

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
        self.last_prompt = prompt
        return self.response_data


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
    mock_payload = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "Web開発の基礎と環境構築",
                "rows": [
                    {
                        "session_number": "第1コマ",
                        "topic": "Webの仕組みと基本",
                        "activities": "スライドを用いた講義と概要説明",
                        "allocated_minutes": 45,
                        "source_slides": [1],
                    },
                    {
                        "session_number": "第1コマ",
                        "topic": "HTML基本タグの記法",
                        "activities": "エディタを用いたハンズオン作成演習",
                        "allocated_minutes": 45,
                        "source_slides": [2],
                    },
                ],
                "total_minutes": 90,
            }
        ],
        "unassigned_slides": [],
    }

    client = FakeMappingClient(mock_payload)
    mapper = SessionMapper(config=sample_config, client=client)

    result = mapper.map_sessions(sample_slide_analyses)

    assert client.call_count == 1
    assert "Web開発入門" in client.last_prompt
    assert "導入・開発環境" in client.last_prompt
    assert "タグの基本と演習" in client.last_prompt

    sessions = getattr(result, "sessions")
    assert len(sessions) == 1
    session_1 = sessions[0]
    assert session_1.session_number == 1
    assert session_1.session_title == "Web開発の基礎と環境構築"
    assert session_1.total_minutes == 90
    assert len(session_1.rows) == 2
    assert session_1.rows[0].topic == "Webの仕組みと基本"
    assert session_1.rows[0].source_slides == [1]
    assert session_1.rows[1].source_slides == [2]


def test_session_mapper_recalculates_total_minutes(
    sample_config: VisshoConfig,
    sample_slide_analyses: list[SlideAnalysisResult],
) -> None:
    # LLM returned total_minutes=0 by mistake
    mock_payload = {
        "sessions": [
            {
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
        ],
        "unassigned_slides": [],
    }

    client = FakeMappingClient(mock_payload)
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
    mock_payload = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "Web入門",
                "rows": [
                    {
                        "session_number": "1",
                        "topic": "導入",
                        "activities": "解説",
                        "allocated_minutes": 90,
                        "source_slides": [1],
                    }
                ],
                "total_minutes": 90,
            }
        ],
        "unassigned_slides": [2],
    }

    client = FakeMappingClient(mock_payload)
    mapper = SessionMapper(config=sample_config, client=client)

    result = mapper.map_sessions(sample_slide_analyses)
    assert getattr(result, "unassigned_slides") == [2]
