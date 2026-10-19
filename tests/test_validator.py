"""Tests for deterministic curriculum validator."""

import pytest
from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig
from vissho.core.schema import create_curriculum_plan_model
from vissho.core.validator import validate_curriculum_plan


@pytest.fixture
def sample_config() -> VisshoConfig:
    return VisshoConfig(
        prerequisites=Prerequisites(
            purpose="テスト講座",
            target_audience="専門学校生",
            total_sessions=2,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号"),
            ColumnDefinition(name="topic", description="単元"),
            ColumnDefinition(name="allocated_minutes", description="配当時間"),
            ColumnDefinition(name="source_slides", description="出典スライド"),
        ],
    )


def test_validate_perfect_plan(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマ",
                    "rows": [
                        {
                            "session_number": "第1コマ",
                            "topic": "導入",
                            "allocated_minutes": 90,
                            "source_slides": [1, 2],
                        }
                    ],
                    "total_minutes": 90,
                },
                {
                    "session_number": 2,
                    "session_title": "第2コマ",
                    "rows": [
                        {
                            "session_number": "第2コマ",
                            "topic": "展開",
                            "allocated_minutes": 90,
                            "source_slides": [3],
                        }
                    ],
                    "total_minutes": 90,
                },
            ],
            "unassigned_slides": [4],
        }
    )

    report = validate_curriculum_plan(plan, sample_config, all_slide_numbers=[1, 2, 3, 4])

    assert report.is_valid is True
    assert report.total_sessions_valid is True
    assert report.total_sessions_actual == 2
    assert report.total_minutes_actual == 180
    assert report.total_minutes_difference == 0
    assert report.referenced_slides == [1, 2, 3]
    assert report.unassigned_slides == [4]
    assert report.missing_slides == []
    assert len(report.errors) == 0


def test_validate_time_mismatch(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマ",
                    "rows": [
                        {
                            "session_number": "1",
                            "topic": "導入",
                            "allocated_minutes": 80,  # 10分不足
                            "source_slides": [1],
                        }
                    ],
                    "total_minutes": 80,
                },
                {
                    "session_number": 2,
                    "session_title": "第2コマ",
                    "rows": [
                        {
                            "session_number": "2",
                            "topic": "展開",
                            "allocated_minutes": 100,  # 10分超過
                            "source_slides": [2],
                        }
                    ],
                    "total_minutes": 100,
                },
            ],
            "unassigned_slides": [],
        }
    )

    report = validate_curriculum_plan(plan, sample_config, all_slide_numbers=[1, 2])

    assert report.is_valid is False
    assert report.session_validations[0].difference == -10
    assert report.session_validations[0].is_valid is False
    assert report.session_validations[1].difference == 10
    assert report.session_validations[1].is_valid is False
    assert any("時間不足" in err for err in report.errors)
    assert any("時間超過" in err for err in report.errors)


def test_validate_missing_slides(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    plan = plan_cls.model_validate(
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
                },
                {
                    "session_number": 2,
                    "session_title": "第2コマ",
                    "rows": [
                        {
                            "session_number": "2",
                            "topic": "展開",
                            "allocated_minutes": 90,
                            "source_slides": [2],
                        }
                    ],
                    "total_minutes": 90,
                },
            ],
            "unassigned_slides": [],
        }
    )

    # All slides include 1, 2, 3, 4 -> 3 and 4 are missing
    report = validate_curriculum_plan(plan, sample_config, all_slide_numbers=[1, 2, 3, 4])

    assert report.is_valid is False
    assert report.missing_slides == [3, 4]
    assert any("未言及スライドが存在します" in err for err in report.errors)


def test_validate_sessions_count_mismatch(sample_config: VisshoConfig) -> None:
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    plan = plan_cls.model_validate(
        {
            "sessions": [
                {
                    "session_number": 1,
                    "session_title": "第1コマのみ",
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

    report = validate_curriculum_plan(plan, sample_config, all_slide_numbers=[1])

    assert report.is_valid is False
    assert report.total_sessions_valid is False
    assert report.total_sessions_actual == 1
    assert any("コマ数不一致" in err for err in report.errors)
