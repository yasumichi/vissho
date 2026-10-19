"""Tests for Phase 3 ConsistencyReviewer."""

from typing import Any
import pytest
from pydantic import BaseModel

from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig
from vissho.core.schema import create_curriculum_plan_model
from vissho.pipeline.phase3_review import ConsistencyReviewer, ReviewResult


class FakeReviewClient:
    """Fake LLM client returning structured refined plans."""

    def __init__(self, refined_data: dict[str, Any]) -> None:
        self.refined_data = refined_data
        self.call_count: int = 0
        self.last_prompt: str = ""

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
        return self.refined_data


@pytest.fixture
def sample_config() -> VisshoConfig:
    return VisshoConfig(
        prerequisites=Prerequisites(
            purpose="テスト講座",
            target_audience="専門学校生",
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


def test_review_already_valid_skips_refinement(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    valid_plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマ",
                    "rows": [
                        {
                            "session_number": "1",
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
    )

    client = FakeReviewClient({})
    reviewer = ConsistencyReviewer(config=sample_config, client=client)

    result = reviewer.review_and_refine(valid_plan, all_slide_numbers=[1], force_refine=False)

    assert isinstance(result, ReviewResult)
    assert result.refined is False
    assert result.validation_report.is_valid is True
    assert client.call_count == 0


def test_review_invalid_triggers_refinement(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    # Invalid: 80 mins instead of 90
    invalid_plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマ",
                    "rows": [
                        {
                            "session_number": "1",
                            "topic": "導入",
                            "allocated_minutes": 80,
                            "source_slides": [1],
                        }
                    ],
                    "total_minutes": 80,
                }
            ],
            "unassigned_slides": [],
        }
    )

    # Refined payload corrects time to 90
    refined_payload = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "第1コマ (推敲後)",
                "rows": [
                    {
                        "session_number": "1",
                        "topic": "導入と基礎",
                        "allocated_minutes": 90,
                        "source_slides": [1],
                    }
                ],
                "total_minutes": 90,
            }
        ],
        "unassigned_slides": [],
    }

    client = FakeReviewClient(refined_payload)
    reviewer = ConsistencyReviewer(config=sample_config, client=client)

    result = reviewer.review_and_refine(invalid_plan, all_slide_numbers=[1])

    assert result.refined is True
    assert client.call_count == 1
    assert "自動検証レポート（指摘事項）" in client.last_prompt
    assert "第1コマの時間不足" in client.last_prompt
    assert result.validation_report.is_valid is True
    assert result.curriculum_plan.sessions[0].session_title == "第1コマ (推敲後)"
    assert result.curriculum_plan.sessions[0].total_minutes == 90


def test_review_force_refine_on_valid_plan(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    valid_plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマ",
                    "rows": [
                        {
                            "session_number": "1",
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
    )

    refined_payload = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "第1コマ (教育的推敲版)",
                "rows": [
                    {
                        "session_number": "1",
                        "topic": "導入と基礎",
                        "allocated_minutes": 90,
                        "source_slides": [1],
                    }
                ],
                "total_minutes": 90,
            }
        ],
        "unassigned_slides": [],
    }

    client = FakeReviewClient(refined_payload)
    reviewer = ConsistencyReviewer(config=sample_config, client=client)

    result = reviewer.review_and_refine(valid_plan, all_slide_numbers=[1], force_refine=True)

    assert result.refined is True
    assert client.call_count == 1
    assert result.curriculum_plan.sessions[0].session_title == "第1コマ (教育的推敲版)"
