"""Tests for LLM client and prompt rendering."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from vissho.config import Prerequisites
from vissho.llm.client import (
    OllamaClient,
    SlideAnalysisOutput,
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
