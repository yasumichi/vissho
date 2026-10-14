"""Configuration models and loader for vissho."""

from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field, field_validator


class RubricItem(BaseModel):
    """Rubric assessment criteria for a grade level."""

    grade: str = Field(..., description="Grade identifier (e.g., A, B, C)")
    criteria: str = Field(..., description="Evaluation criteria for the grade")


class Prerequisites(BaseModel):
    """Educational prerequisites and course constraints."""

    purpose: str = Field(..., description="Goal and purpose of the course")
    target_audience: str = Field(..., description="Target audience and level")
    prerequisite_knowledge: str | None = Field(
        default=None, description="Assumed prior knowledge or skills"
    )
    total_sessions: int = Field(..., gt=0, description="Total number of sessions (コマ数)")
    session_minutes: int = Field(
        ..., gt=0, description="Duration per session in minutes (1コマあたりの時間)"
    )
    rubric: list[RubricItem] = Field(
        default_factory=list, description="Rubric assessment criteria"
    )

    @property
    def total_minutes(self) -> int:
        """Total course duration in minutes."""
        return self.total_sessions * self.session_minutes


class ColumnDefinition(BaseModel):
    """Definition of an output table column."""

    name: str = Field(
        ...,
        description="Column field name (used in model and headers, identifier format recommended)",
    )
    description: str = Field(..., description="Explanation/prompt for the column content")
    width: int = Field(default=20, gt=0, description="Recommended column width in Excel")
    required: bool = Field(default=True, description="Whether this column is required")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Column name cannot be empty")
        return stripped


class SupplementaryNote(BaseModel):
    """Implicit knowledge or supplementary instruction note for a specific slide."""

    slide_number: int = Field(..., ge=1, description="Target slide number (1-indexed)")
    note: str = Field(..., description="Instructor note or implicit explanation")


class VisshoConfig(BaseModel):
    """Root configuration for vissho execution."""

    prerequisites: Prerequisites
    columns: list[ColumnDefinition] = Field(
        ..., min_length=1, description="Output table column definitions"
    )
    supplementary_notes: list[SupplementaryNote] = Field(
        default_factory=list,
        description="Supplementary notes and implicit knowledge by slide number",
    )

    def get_notes_for_slide(self, slide_number: int) -> list[str]:
        """Return all supplementary notes associated with the given slide number."""
        return [
            item.note
            for item in self.supplementary_notes
            if item.slide_number == slide_number
        ]


DEFAULT_CONFIG_TEMPLATE = """# vissho 設定ファイル (config.yaml)

# 教育の前提情報
prerequisites:
  purpose: "〇〇技術の基礎概念を理解し、簡単なアプリケーションを自力で構築できる。"
  target_audience: "情報系専門学校 1年生（基礎的なプログラミング知識を有する）"
  prerequisite_knowledge: "Python の基本文法（変数、関数、制御構文）"
  total_sessions: 4       # コマ数
  session_minutes: 90     # 1コマあたりの時間（分）
  rubric:
    - grade: "A"
      criteria: "〇〇の概念を正しく理解し、発展的な課題を独力で解決できる。"
    - grade: "B"
      criteria: "指示に従って基本機能を実装できる。"
    - grade: "C"
      criteria: "基本用語を理解しているが、実装には補助が必要である。"

# 出力する表の列定義
columns:
  - name: "session_number"
    description: "コマ番号（例: 第1コマ）"
    width: 12
  - name: "topic"
    description: "単元・大項目"
    width: 20
  - name: "learning_objectives"
    description: "学生の到達目標・ねらい"
    width: 30
  - name: "activities"
    description: "具体的な学習活動・授業展開"
    width: 40
  - name: "allocated_minutes"
    description: "配当時間（分）"
    width: 12
  - name: "remarks"
    description: "指導上の留意点・準備物・教員の補足説明（暗黙知）"
    width: 30
  - name: "source_slides"
    description: "出典スライド番号一覧"
    width: 16

# 補足・暗黙知の入力（オプション: スライド画像だけでは読み取れない教員の補足説明）
supplementary_notes:
  - slide_number: 5
    note: "ここの図は受講生がつまずきやすいので、板書で具体例を補足して説明する。"
  - slide_number: 12
    note: "時間が押しやすいため、演習課題の一部は持ち帰り宿題としてもよい。"
"""


def load_config(path: str | Path) -> VisshoConfig:
    """Load configuration from a YAML or JSON file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid configuration format in {config_path}: expected dictionary")

    return VisshoConfig.model_validate(data)


def save_config(config: VisshoConfig, path: str | Path) -> None:
    """Save configuration to a YAML file."""
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            config.model_dump(mode="json"),
            f,
            allow_unicode=True,
            sort_keys=False,
        )
