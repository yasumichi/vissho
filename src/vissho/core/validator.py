"""Deterministic validator for curriculum plan sessions, time allocations, and slide coverage."""

from typing import Any
from pydantic import BaseModel, Field

from vissho.config import VisshoConfig


class SessionValidation(BaseModel):
    """Validation result for an individual class session."""

    session_number: int = Field(..., description="コマ番号")
    session_title: str = Field(..., description="単元・テーマ")
    allocated_minutes: int = Field(..., description="このコマの各行の配当時間合計")
    target_minutes: int = Field(..., description="目標時間 (session_minutes)")
    difference: int = Field(..., description="配当時間と目標時間の差分 (allocated - target)")
    is_valid: bool = Field(..., description="目標時間と一致しているかどうか")


class ValidationReport(BaseModel):
    """Comprehensive validation report for a curriculum plan."""

    is_valid: bool = Field(..., description="すべての必須制約（コマ数、時間、スライド網羅性）を満たしているか")
    total_sessions_valid: bool = Field(..., description="コマ数が prerequisites.total_sessions と一致しているか")
    total_sessions_actual: int = Field(..., description="実際のコマ数")
    total_sessions_target: int = Field(..., description="目標のコマ数")
    total_minutes_actual: int = Field(..., description="全コマの配当時間総計")
    total_minutes_target: int = Field(..., description="全体の目標時間総計 (total_sessions * session_minutes)")
    total_minutes_difference: int = Field(..., description="総時間の差分 (actual - target)")
    session_validations: list[SessionValidation] = Field(
        default_factory=list, description="各コマの検証結果リスト"
    )
    referenced_slides: list[int] = Field(
        default_factory=list, description="いずれかの行で参照されているスライド番号一覧 (重複排除・ソート済)"
    )
    unassigned_slides: list[int] = Field(
        default_factory=list, description="カリキュラムから除外・自習等に設定されたスライド番号一覧"
    )
    missing_slides: list[int] = Field(
        default_factory=list,
        description="全スライド中、指導案行にも unassigned_slides にも含まれていない未言及スライド番号一覧",
    )
    invalid_slide_references: list[int] = Field(
        default_factory=list,
        description="全スライド範囲外の存在しないスライド番号への不正な参照一覧",
    )
    errors: list[str] = Field(default_factory=list, description="エラーメッセージ一覧")
    warnings: list[str] = Field(default_factory=list, description="警告メッセージ一覧")


def validate_curriculum_plan(
    curriculum_plan: BaseModel | dict[str, Any],
    config: VisshoConfig,
    all_slide_numbers: list[int] | set[int] | int | None = None,
) -> ValidationReport:
    """Deterministically validate session time sums, total duration, and slide coverage.

    Args:
        curriculum_plan: The CurriculumPlan model instance or dict.
        config: Vissho configuration containing prerequisites and constraints.
        all_slide_numbers: List/set of all available slide numbers, or total count (e.g., 20).
    """
    if isinstance(curriculum_plan, dict):
        sessions_data = curriculum_plan.get("sessions", [])
        unassigned_slides_raw = curriculum_plan.get("unassigned_slides", [])
    else:
        sessions_data = getattr(curriculum_plan, "sessions", [])
        unassigned_slides_raw = getattr(curriculum_plan, "unassigned_slides", [])

    target_sessions = config.prerequisites.total_sessions
    target_session_minutes = config.prerequisites.session_minutes
    target_total_minutes = config.prerequisites.total_minutes

    actual_sessions_count = len(sessions_data)
    total_sessions_valid = actual_sessions_count == target_sessions

    errors: list[str] = []
    warnings: list[str] = []

    if not total_sessions_valid:
        errors.append(
            f"コマ数不一致: 目標 {target_sessions} コマに対して、実際は {actual_sessions_count} コマです。"
        )

    session_validations: list[SessionValidation] = []
    total_minutes_actual = 0
    referenced_slides_set: set[int] = set()

    for idx, session in enumerate(sessions_data, start=1):
        if isinstance(session, dict):
            s_num = session.get("session_number", idx)
            s_title = session.get("session_title", f"第{idx}コマ")
            rows = session.get("rows", [])
        else:
            s_num = getattr(session, "session_number", idx)
            s_title = getattr(session, "session_title", f"第{idx}コマ")
            rows = getattr(session, "rows", [])

        # Calculate total allocated minutes in this session
        session_allocated_minutes = 0
        for row in rows:
            if isinstance(row, dict):
                mins = row.get("allocated_minutes", 0)
                slides = row.get("source_slides") or row.get("source_slide_numbers") or []
            else:
                mins = getattr(row, "allocated_minutes", 0)
                slides = getattr(row, "source_slides", None) or getattr(row, "source_slide_numbers", None) or []

            if isinstance(mins, (int, float)):
                session_allocated_minutes += int(mins)

            if isinstance(slides, list):
                for s in slides:
                    if isinstance(s, int):
                        referenced_slides_set.add(s)

        diff = session_allocated_minutes - target_session_minutes
        s_valid = diff == 0
        total_minutes_actual += session_allocated_minutes

        if not s_valid:
            if diff > 0:
                errors.append(f"第{s_num}コマの時間超過: {session_allocated_minutes}分 (目標: {target_session_minutes}分, +{diff}分)")
            else:
                errors.append(f"第{s_num}コマの時間不足: {session_allocated_minutes}分 (目標: {target_session_minutes}分, {diff}分)")

        session_validations.append(
            SessionValidation(
                session_number=s_num,
                session_title=s_title,
                allocated_minutes=session_allocated_minutes,
                target_minutes=target_session_minutes,
                difference=diff,
                is_valid=s_valid,
            )
        )

    total_diff = total_minutes_actual - target_total_minutes
    if total_diff != 0:
        errors.append(
            f"総時間不一致: 全コマ合計 {total_minutes_actual}分 (目標: {target_total_minutes}分, 差分: {total_diff:+d}分)"
        )

    # Process slide numbers coverage
    referenced_slides = sorted(referenced_slides_set)
    unassigned_slides = sorted(set(unassigned_slides_raw))

    missing_slides: list[int] = []
    invalid_slide_references: list[int] = []

    if all_slide_numbers is not None:
        if isinstance(all_slide_numbers, int):
            expected_set = set(range(1, all_slide_numbers + 1))
        else:
            expected_set = set(all_slide_numbers)

        covered_set = referenced_slides_set.union(unassigned_slides)
        missing_slides = sorted(expected_set - covered_set)
        invalid_slide_references = sorted(referenced_slides_set - expected_set)

        if missing_slides:
            errors.append(f"未言及スライドが存在します: {missing_slides}")
        if invalid_slide_references:
            warnings.append(f"存在しないスライド番号への参照があります: {invalid_slide_references}")

    # Overall validity requires: correct sessions count, all sessions match target time, no missing slides
    all_sessions_valid = all(sv.is_valid for sv in session_validations)
    is_valid = total_sessions_valid and all_sessions_valid and (len(missing_slides) == 0)

    return ValidationReport(
        is_valid=is_valid,
        total_sessions_valid=total_sessions_valid,
        total_sessions_actual=actual_sessions_count,
        total_sessions_target=target_sessions,
        total_minutes_actual=total_minutes_actual,
        total_minutes_target=target_total_minutes,
        total_minutes_difference=total_diff,
        session_validations=session_validations,
        referenced_slides=referenced_slides,
        unassigned_slides=unassigned_slides,
        missing_slides=missing_slides,
        invalid_slide_references=invalid_slide_references,
        errors=errors,
        warnings=warnings,
    )
