"""Tests for LLM client and prompt rendering."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from vissho.config import Prerequisites
from vissho.llm.client import (
    OllamaClient,
    SlideAnalysisOutput,
    render_session_mapping_prompt,
    render_slide_analysis_prompt,
)


@pytest.fixture
def sample_prerequisites() -> Prerequisites:
    return Prerequisites(
        purpose="Pythonの基礎文法習得",
        target_audience="専門学校1年生",
        prerequisite_knowledge="PC基本操作",
        total_sessions=2,
        session_minutes=90,
    )


def test_render_slide_analysis_prompt_without_notes(sample_prerequisites: Prerequisites) -> None:
    prompt = render_slide_analysis_prompt(
        prerequisites=sample_prerequisites,
        slide_number=1,
    )
    assert "Pythonの基礎文法習得" in prompt
    assert "専門学校1年生" in prompt
    assert "PC基本操作" in prompt
    assert "スライド番号: 1" in prompt
    assert "補足・暗黙知メモ一覧" not in prompt


def test_render_slide_analysis_prompt_with_notes(sample_prerequisites: Prerequisites) -> None:
    prompt = render_slide_analysis_prompt(
        prerequisites=sample_prerequisites,
        slide_number=5,
        supplementary_notes=["受講生がつまずきやすいので具体例を板書"],
    )
    assert "スライド番号: 5" in prompt
    assert "補足・暗黙知メモ一覧" in prompt
    assert "受講生がつまずきやすいので具体例を板書" in prompt


def test_slide_analysis_output_schema() -> None:
    schema = SlideAnalysisOutput.model_json_schema()
    assert "title" in schema["properties"]
    assert "topics" in schema["properties"]
    assert "estimated_minutes" in schema["properties"]


def test_ollama_client_analyze_slide_mock(tmp_path: Path) -> None:
    dummy_image = tmp_path / "slide_01.png"
    dummy_image.write_bytes(b"dummy image data")

    client = OllamaClient(default_model="qwen2.5-vl")

    mock_response = {
        "message": {
            "content": (
                '{"title": "変数とデータ型", "topics": ["int", "str"], '
                '"key_points": ["値の保持"], "suggested_activities": ["演習"], '
                '"estimated_minutes": 10, "instructor_notes": ["型エラーに注意"]}'
            )
        }
    }

    with patch.object(client._client, "chat", return_value=mock_response) as mock_chat:
        result = client.analyze_slide(dummy_image, prompt="analyze")

        assert isinstance(result, SlideAnalysisOutput)
        assert result.title == "変数とデータ型"
        assert result.estimated_minutes == 10
        assert "int" in result.topics
        mock_chat.assert_called_once()


def test_ollama_client_file_not_found(tmp_path: Path) -> None:
    client = OllamaClient()
    missing_image = tmp_path / "non_existent.png"
    with pytest.raises(FileNotFoundError):
        client.analyze_slide(missing_image, prompt="analyze")


def test_render_session_mapping_prompt(sample_prerequisites: Prerequisites) -> None:
    from vissho.config import ColumnDefinition

    columns = [
        ColumnDefinition(name="topic", description="単元"),
        ColumnDefinition(name="allocated_minutes", description="配当時間"),
    ]
    dummy_analyses = [
        {
            "slide_number": 1,
            "analysis": {
                "title": "ガイダンス",
                "topics": ["概要", "環境"],
                "key_points": ["自己紹介"],
                "suggested_activities": ["解説"],
                "estimated_minutes": 15,
            },
            "supplementary_notes": ["PC接続を確認すること"],
        }
    ]

    prompt = render_session_mapping_prompt(
        prerequisites=sample_prerequisites,
        columns=columns,
        slide_analyses=dummy_analyses,
    )
    assert "Pythonの基礎文法習得" in prompt
    assert "全コマ数: 2 コマ" in prompt
    assert "**topic**: 単元" in prompt
    assert "■ スライド番号: 1" in prompt
    assert "ガイダンス" in prompt
    assert "PC接続を確認すること" in prompt


def test_ollama_client_generate_structured() -> None:
    from pydantic import BaseModel, Field

    class SimpleSchema(BaseModel):
        summary: str = Field(..., description="Summary")
        count: int = Field(..., description="Count")

    client = OllamaClient()
    mock_response = {
        "message": {
            "content": '{"summary": "テスト概要", "count": 3}'
        }
    }

    with patch.object(client._client, "chat", return_value=mock_response) as mock_chat:
        result = client.generate_structured(
            prompt="summarize",
            schema=SimpleSchema,
            system_prompt="system message",
        )
        assert result == {"summary": "テスト概要", "count": 3}
        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args[1]
        assert call_kwargs["messages"][0]["content"] == "system message"
        assert call_kwargs["messages"][1]["content"] == "summarize"

