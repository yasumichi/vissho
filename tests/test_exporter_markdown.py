"""Tests for Markdown exporter."""

from pathlib import Path
import pytest

from vissho.config import ColumnDefinition, Prerequisites, VisshoConfig
from vissho.core.schema import create_curriculum_plan_model
from vissho.core.validator import validate_curriculum_plan
from vissho.exporter.markdown import export_to_markdown


@pytest.fixture
def sample_config() -> VisshoConfig:
    return VisshoConfig(
        prerequisites=Prerequisites(
            purpose="テスト講座（Web開発）",
            target_audience="専門学校1年生",
            prerequisite_knowledge="HTML/CSS",
            total_sessions=2,
            session_minutes=90,
        ),
        columns=[
            ColumnDefinition(name="session_number", description="コマ番号", width=12),
            ColumnDefinition(name="topic", description="単元", width=25),
            ColumnDefinition(name="allocated_minutes", description="配当時間", width=14),
            ColumnDefinition(name="activities", description="活動", width=40),
            ColumnDefinition(name="source_slides", description="出典スライド", width=16),
        ],
    )


@pytest.fixture
def sample_plan_data() -> dict:
    return {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "Webフロントエンド基礎",
                "rows": [
                    {
                        "session_number": "第1コマ",
                        "topic": "JavaScript導入 | 構文",
                        "allocated_minutes": 90,
                        "activities": "変数の宣言\nコンソール出力",
                        "source_slides": [1, 2],
                    }
                ],
                "total_minutes": 90,
            },
            {
                "session_number": 2,
                "session_title": "DOM操作",
                "rows": [
                    {
                        "session_number": "第2コマ",
                        "topic": "イベント処理",
                        "allocated_minutes": 90,
                        "activities": "ボタンクリック時の動作作成",
                        "source_slides": [3],
                    }
                ],
                "total_minutes": 90,
            },
        ],
        "unassigned_slides": [4],
    }


def test_export_to_markdown_string_and_file(sample_config: VisshoConfig, sample_plan_data: dict, tmp_path: Path) -> None:
    """Test generating Markdown string and writing to file."""
    target_file = tmp_path / "plan.md"
    result = export_to_markdown(sample_plan_data, sample_config, output_path=target_file)

    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == result

    # Check headers and prerequisites
    assert "# 学習指導案: テスト講座（Web開発）" in result
    assert "専門学校1年生" in result
    assert "HTML/CSS" in result
    assert "全 2 コマ" in result

    # Check GFM table structure
    assert "| session_number | topic | allocated_minutes | activities | source_slides |" in result
    assert "| --- | --- | --- | --- | --- |" in result

    # Check escaped characters: pipe escaped, newline replaced with <br>
    assert "JavaScript導入 \\| 構文" in result
    assert "変数の宣言<br>コンソール出力" in result

    # Check unassigned slides
    assert "## 未割り当てスライド" in result
    assert "4" in result


def test_export_to_markdown_with_validation_report(sample_config: VisshoConfig, sample_plan_data: dict) -> None:
    """Test Markdown export includes validation section when report is provided."""
    plan_cls = create_curriculum_plan_model(sample_config.columns)
    model_plan = plan_cls.model_validate(sample_plan_data)
    report = validate_curriculum_plan(model_plan, sample_config, all_slide_numbers=[1, 2, 3, 4])

    result = export_to_markdown(model_plan, sample_config, validation_report=report)

    assert "## 整合性検証レポート" in result
    assert "合格 (PASSED)" in result
    assert "コマ別配当時間検証" in result
    assert "第1コマ" in result
    assert "第2コマ" in result


def test_export_to_markdown_with_rubric_and_errors(tmp_path: Path) -> None:
    """Test Markdown export with rubric evaluation criteria and validation errors."""
    from vissho.config import RubricItem
    from vissho.core.validator import SessionValidation, ValidationReport

    config = VisshoConfig(
        prerequisites=Prerequisites(
            purpose="ルーブリック付き講座",
            target_audience="受講生",
            total_sessions=1,
            session_minutes=90,
            rubric=[
                RubricItem(grade="A", criteria="独力で応用課題を解ける"),
                RubricItem(grade="B", criteria="基本課題を解ける"),
            ],
        ),
        columns=[
            ColumnDefinition(name="topic", description="単元"),
            ColumnDefinition(name="allocated_minutes", description="配当時間"),
        ],
    )

    report = ValidationReport(
        is_valid=False,
        total_sessions_valid=True,
        total_sessions_actual=1,
        total_sessions_target=1,
        total_minutes_actual=60,
        total_minutes_target=90,
        total_minutes_difference=-30,
        session_validations=[
            SessionValidation(
                session_number=1,
                session_title="短縮コマ",
                allocated_minutes=60,
                target_minutes=90,
                difference=-30,
                is_valid=False,
            )
        ],
        referenced_slides=[1],
        unassigned_slides=[],
        missing_slides=[],
        invalid_slide_references=[],
        errors=["配当時間不足: 目標90分に対して60分です。"],
        warnings=["演習時間が短いです。"],
    )

    plan_data = {
        "sessions": [
            {
                "session_number": 1,
                "session_title": "短縮コマ",
                "rows": [
                    {
                        "topic": "基礎",
                        "allocated_minutes": 60,
                    }
                ],
                "total_minutes": 60,
            }
        ],
        "unassigned_slides": [],
    }

    result = export_to_markdown(plan_data, config, validation_report=report)
    assert "### ルーブリック評価基準" in result
    assert "独力で応用課題を解ける" in result
    assert "指摘事項あり (ISSUES DETECTED)" in result
    assert "❌ 配当時間不足" in result
    assert "⚠️ 演習時間が短いです。" in result
    assert "❌ 差分あり" in result
