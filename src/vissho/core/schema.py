"""Core domain and dynamic schema generation for vissho."""

from typing import Any, get_origin
from pydantic import BaseModel, Field, create_model

from vissho.config import ColumnDefinition

SPECIAL_FIELD_NAMES = {"allocated_minutes", "source_slides", "source_slide_numbers"}


def create_instruction_row_model(
    columns: list[ColumnDefinition],
    model_name: str = "InstructionRow",
) -> type[BaseModel]:
    """Create a dynamic Pydantic model for a single row in the instruction plan table.

    Builds fields based on user-defined columns, ensuring essential columns
    (allocated_minutes and source_slide_numbers) are present for calculation
    and traceability.
    """
    field_definitions: dict[str, Any] = {}
    included_names = {col.name for col in columns}

    for col in columns:
        col_name = col.name
        desc = col.description or ""
        if col_name == "allocated_minutes":
            field_definitions[col_name] = (
                int,
                Field(ge=0, description=desc or "配当時間（分）"),
            )
        elif col_name in ("source_slides", "source_slide_numbers"):
            field_definitions[col_name] = (
                list[int],
                Field(default_factory=list, description=desc or "出典スライド番号一覧"),
            )
        else:
            if col.required:
                field_definitions[col_name] = (str, Field(description=desc))
            else:
                field_definitions[col_name] = (
                    str | None,
                    Field(default=None, description=desc),
                )

    # Ensure internal traceability column exists
    if "source_slide_numbers" not in included_names and "source_slides" not in included_names:
        field_definitions["source_slide_numbers"] = (
            list[int],
            Field(default_factory=list, description="出典スライド番号一覧"),
        )

    # Ensure allocated_minutes exists for time calculations
    if "allocated_minutes" not in included_names:
        field_definitions["allocated_minutes"] = (
            int,
            Field(ge=0, description="配当時間（分）"),
        )

    return create_model(model_name, **field_definitions)


def create_session_plan_model(
    row_model: type[BaseModel],
    model_name: str = "SessionPlan",
) -> type[BaseModel]:
    """Create a dynamic model representing a single class session (1コマ)."""
    field_definitions: dict[str, Any] = {
        "session_number": (int, Field(..., ge=1, description="コマ番号 (1-indexed)")),
        "session_title": (str, Field(..., description="このコマの単元または主要テーマ")),
        "rows": (list[row_model], Field(..., description="このコマを構成する指導案行リスト")),
        "total_minutes": (int, Field(..., ge=0, description="このコマの合計配当時間（分）")),
    }
    return create_model(model_name, **field_definitions)


def create_curriculum_plan_model(
    columns: list[ColumnDefinition],
    model_name: str = "CurriculumPlan",
) -> type[BaseModel]:
    """Create the root curriculum model containing all sessions and dynamic row schemas."""
    row_model = create_instruction_row_model(columns, model_name=f"{model_name}Row")
    session_model = create_session_plan_model(row_model, model_name=f"{model_name}Session")

    field_definitions: dict[str, Any] = {
        "sessions": (list[session_model], Field(..., description="全コマの指導案リスト")),
        "unassigned_slides": (
            list[int],
            Field(
                default_factory=list,
                description="指導案に割り当てられなかったスライド番号一覧（ある場合）",
            ),
        ),
    }
    return create_model(model_name, **field_definitions)


class SessionOutline(BaseModel):
    """Outline for a single session in Step 2-A mapping."""

    session_number: int = Field(..., ge=1, description="コマ番号 (1-indexed)")
    session_title: str = Field(..., description="このコマの単元または主要テーマ")
    slide_numbers: list[int] = Field(
        default_factory=list, description="このコマに割り当てるスライド番号一覧"
    )


class CourseOutline(BaseModel):
    """Course outline generated in Step 2-A mapping slides to sessions."""

    sessions: list[SessionOutline] = Field(..., description="全コマのアウトライン一覧")
    unassigned_slides: list[int] = Field(
        default_factory=list,
        description="指導案に割り当てられなかったスライド番号一覧（ある場合）",
    )


def get_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Generate a clean JSON schema dictionary suitable for Ollama's format: json."""
    return model.model_json_schema()
