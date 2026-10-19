"""Tests for Phase 1 SlideAnalyzer."""

from pathlib import Path
from PIL import Image
import pytest

from vissho.config import (
    ColumnDefinition,
    Prerequisites,
    SupplementaryNote,
    VisshoConfig,
)
from vissho.llm.client import SlideAnalysisOutput
from vissho.pipeline.phase1_analyze import SlideAnalysisResult, SlideAnalyzer
from vissho.utils.cache import SlideCache


def _create_dummy_png(path: Path, color: str = "blue") -> None:
    img = Image.new("RGB", (32, 32), color=color)
    img.save(path, format="PNG")


class FakeLLMClient:
    """Fake LLM client for testing without Ollama service."""

    def __init__(self, default_model: str = "fake-model") -> None:
        self.default_model = default_model
        self.call_count = 0
        self.last_prompt = ""
        self.last_image_path: Path | None = None

    def analyze_slide(
        self,
        image_path: Path,
        prompt: str,
        model: str | None = None,
    ) -> SlideAnalysisOutput:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_image_path = image_path

        return SlideAnalysisOutput(
            title=f"Title for {image_path.name}",
            topics=["Topic A", "Topic B"],
            key_points=["Point 1", "Point 2"],
            suggested_activities=["Lecture", "Exercise"],
            estimated_minutes=15,
            instructor_notes=["Careful with syntax"],
        )


@pytest.fixture
def sample_config() -> VisshoConfig:
    return VisshoConfig(
        prerequisites=Prerequisites(
            purpose="Web開発入門",
            target_audience="専門学校生",
            total_sessions=4,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号"),
            ColumnDefinition(name="topic", description="単元"),
            ColumnDefinition(name="activities", description="活動"),
            ColumnDefinition(name="allocated_minutes", description="配当時間"),
        ],
        supplementary_notes=[
            SupplementaryNote(
                slide_number=2,
                note="スライド2ではハンズオン演習を多めに取る",
            )
        ],
    )


def test_analyzer_single_slide(tmp_path: Path, sample_config: VisshoConfig) -> None:
    img_path = tmp_path / "slide_01.png"
    _create_dummy_png(img_path)

    fake_client = FakeLLMClient()
    cache = SlideCache(cache_dir=tmp_path / "cache")
    analyzer = SlideAnalyzer(config=sample_config, client=fake_client, cache=cache)

    result = analyzer.analyze_slide(slide_number=1, image_path=img_path)

    assert isinstance(result, SlideAnalysisResult)
    assert result.slide_number == 1
    assert result.cached is False
    assert result.analysis.title == "Title for slide_01.png"
    assert result.analysis.estimated_minutes == 15
    assert fake_client.call_count == 1

    # Second call should use cache
    result2 = analyzer.analyze_slide(slide_number=1, image_path=img_path)
    assert result2.cached is True
    assert fake_client.call_count == 1  # Not called again

    # Third call with use_cache=False forces re-analysis
    result3 = analyzer.analyze_slide(slide_number=1, image_path=img_path, use_cache=False)
    assert result3.cached is False
    assert fake_client.call_count == 2


def test_analyzer_with_supplementary_notes(tmp_path: Path, sample_config: VisshoConfig) -> None:
    img_path = tmp_path / "slide_02.png"
    _create_dummy_png(img_path)

    fake_client = FakeLLMClient()
    cache = SlideCache(cache_dir=tmp_path / "cache")
    analyzer = SlideAnalyzer(config=sample_config, client=fake_client, cache=cache)

    result = analyzer.analyze_slide(slide_number=2, image_path=img_path)

    assert result.slide_number == 2
    assert "スライド2ではハンズオン演習を多めに取る" in result.supplementary_notes
    assert "スライド2ではハンズオン演習を多めに取る" in fake_client.last_prompt


def test_analyzer_directory(tmp_path: Path, sample_config: VisshoConfig) -> None:
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    _create_dummy_png(slides_dir / "slide_02.png", color="green")
    _create_dummy_png(slides_dir / "slide_01.png", color="red")
    _create_dummy_png(slides_dir / "slide_03.png", color="blue")

    fake_client = FakeLLMClient()
    cache = SlideCache(cache_dir=tmp_path / "cache")
    analyzer = SlideAnalyzer(config=sample_config, client=fake_client, cache=cache)

    progress_log: list[tuple[int, int, int]] = []

    def on_progress(cur: int, total: int, res: SlideAnalysisResult) -> None:
        progress_log.append((cur, total, res.slide_number))

    results = analyzer.analyze_directory(
        directory=slides_dir,
        progress_callback=on_progress,
    )

    assert len(results) == 3
    assert [r.slide_number for r in results] == [1, 2, 3]
    assert len(progress_log) == 3
    assert progress_log == [(1, 3, 1), (2, 3, 2), (3, 3, 3)]
    assert fake_client.call_count == 3
