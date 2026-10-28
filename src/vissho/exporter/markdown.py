"""Markdown exporter for curriculum plans, suitable for terminal preview and documentation."""

from pathlib import Path
from typing import Any
from pydantic import BaseModel

from vissho.config import VisshoConfig
from vissho.core.validator import ValidationReport


def _escape_markdown_cell(value: Any) -> str:
    """Format and escape text for a Markdown table cell."""
    if value is None:
        return ""
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    # Escape pipe characters and replace newlines with HTML line breaks
    text = text.replace("|", "\\|")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    return text.strip()


def export_to_markdown(
    curriculum_plan: BaseModel | dict[str, Any],
    config: VisshoConfig,
    output_path: str | Path | None = None,
    validation_report: ValidationReport | None = None,
) -> str:
    """Export curriculum plan to a GitHub-Flavored Markdown document.

    Args:
        curriculum_plan: Curriculum plan Pydantic model or dict.
        config: Vissho configuration containing prerequisites and column definitions.
        output_path: Optional file path to write Markdown.
        validation_report: Optional validation report to append to the document.

    Returns:
        Generated Markdown string.
    """
    if isinstance(curriculum_plan, BaseModel):
        plan_dict = curriculum_plan.model_dump(mode="json")
    else:
        plan_dict = curriculum_plan

    sessions = plan_dict.get("sessions", [])
    unassigned_slides = plan_dict.get("unassigned_slides", [])

    lines: list[str] = []

    # Title & Prerequisites Header
    lines.append(f"# 学習指導案: {config.prerequisites.purpose}")
    lines.append("")
    lines.append("## 前提情報")
    lines.append(f"- **対象者**: {config.prerequisites.target_audience}")
    if config.prerequisites.prerequisite_knowledge:
        lines.append(f"- **前提知識**: {config.prerequisites.prerequisite_knowledge}")
    lines.append(
        f"- **コマ数・時間**: 全 {config.prerequisites.total_sessions} コマ "
        f"（1コマ {config.prerequisites.session_minutes} 分 / 総時間 {config.prerequisites.total_minutes} 分）"
    )

    if config.prerequisites.rubric:
        lines.append("")
        lines.append("### ルーブリック評価基準")
        for r in config.prerequisites.rubric:
            lines.append(f"- **{r.grade}**: {r.criteria}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Sessions
    for session in sessions:
        s_num = session.get("session_number", 1)
        s_title = session.get("session_title", "")
        s_total = session.get("total_minutes", 0)
        target_mins = config.prerequisites.session_minutes

        lines.append(f"## 第{s_num}コマ: {s_title}")
        lines.append(f"- **合計配当時間**: {s_total} 分 / 目標: {target_mins} 分")
        lines.append("")

        # Table header
        headers = [col.name for col in config.columns]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Table rows
        rows = session.get("rows", [])
        for row in rows:
            row_cells: list[str] = []
            for col in config.columns:
                cell_val = row.get(col.name, "")
                row_cells.append(_escape_markdown_cell(cell_val))
            lines.append("| " + " | ".join(row_cells) + " |")

        lines.append("")

    # Unassigned slides
    if unassigned_slides:
        lines.append("## 未割り当てスライド")
        slides_str = ", ".join(str(s) for s in unassigned_slides)
        lines.append(f"以下のスライドは授業外・自習等に設定されています: {slides_str}")
        lines.append("")

    # Validation Report Summary (if provided)
    if validation_report is not None:
        lines.append("---")
        lines.append("")
        lines.append("## 整合性検証レポート")
        status_label = "合格 (PASSED)" if validation_report.is_valid else "指摘事項あり (ISSUES DETECTED)"
        lines.append(f"- **検証判定**: **{status_label}**")
        lines.append(
            f"- **コマ数**: {validation_report.total_sessions_actual} / {validation_report.total_sessions_target}"
        )
        lines.append(
            f"- **総時間**: {validation_report.total_minutes_actual} 分 / {validation_report.total_minutes_target} 分 "
            f"(差分: {validation_report.total_minutes_difference:+d} 分)"
        )

        if validation_report.errors:
            lines.append("")
            lines.append("### エラー")
            for err in validation_report.errors:
                lines.append(f"- ❌ {err}")

        if validation_report.warnings:
            lines.append("")
            lines.append("### 警告")
            for warn in validation_report.warnings:
                lines.append(f"- ⚠️ {warn}")

        if validation_report.session_validations:
            lines.append("")
            lines.append("### コマ別配当時間検証")
            lines.append("| コマ | テーマ | 配当時間 | 目標時間 | 差分 | 判定 |")
            lines.append("|---|---|---|---|---|---|")
            for sv in validation_report.session_validations:
                status_icon = "✅ OK" if sv.is_valid else "❌ 差分あり"
                diff_str = f"{sv.difference:+d} 分" if sv.difference != 0 else "0 分"
                lines.append(
                    f"| 第{sv.session_number}コマ | {_escape_markdown_cell(sv.session_title)} | "
                    f"{sv.allocated_minutes} 分 | {sv.target_minutes} 分 | {diff_str} | {status_icon} |"
                )
            lines.append("")

    content = "\n".join(lines).rstrip() + "\n"

    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", encoding="utf-8") as f:
            f.write(content)

    return content


def export_slide_analyses_to_markdown(
    slide_analyses: list[Any],
    output_path: str | Path | None = None,
    title: str = "スライド解析結果一覧",
) -> str:
    """Export Phase 1 slide analysis results to a GitHub-Flavored Markdown table.

    Args:
        slide_analyses: List of SlideAnalysisResult instances or dictionaries.
        output_path: Optional file path to write Markdown.
        title: Title of the document.

    Returns:
        Generated Markdown string.
    """
    lines: list[str] = [
        f"# {title}",
        "",
        f"- **対象スライド数**: {len(slide_analyses)} 枚",
        "",
        "| スライド番号 | タイトル | 主なトピック | 重要ポイント | 想定学習活動 | 目安時間（分） | 指導上の留意点・暗黙知 | 画像ファイル |",
        "| :---: | :--- | :--- | :--- | :--- | ---: | :--- | :--- |",
    ]

    total_est_minutes = 0

    for item in slide_analyses:
        if isinstance(item, BaseModel):
            item_dict = item.model_dump(mode="json")
        elif isinstance(item, dict):
            item_dict = item
        else:
            item_dict = {"slide_number": getattr(item, "slide_number", 0)}

        analysis = item_dict.get("analysis", {})
        if isinstance(analysis, BaseModel):
            analysis = analysis.model_dump(mode="json")

        slide_num = item_dict.get("slide_number", 0)
        slide_title = analysis.get("title", "")
        topics = ", ".join(analysis.get("topics", []))
        key_points = "<br>".join(f"・{p}" for p in analysis.get("key_points", []))
        activities = ", ".join(analysis.get("suggested_activities", []))
        est_minutes = analysis.get("estimated_minutes", 0)
        total_est_minutes += est_minutes if isinstance(est_minutes, int) else 0

        all_notes: list[str] = []
        if analysis.get("instructor_notes"):
            all_notes.extend(analysis["instructor_notes"])
        if item_dict.get("supplementary_notes"):
            all_notes.extend(item_dict["supplementary_notes"])
        notes_str = "<br>".join(f"・{n}" for n in all_notes) if all_notes else ""

        raw_path = item_dict.get("image_path", "")
        img_name = Path(raw_path).name if raw_path else ""

        lines.append(
            f"| {slide_num} | {_escape_markdown_cell(slide_title)} | "
            f"{_escape_markdown_cell(topics)} | {_escape_markdown_cell(key_points)} | "
            f"{_escape_markdown_cell(activities)} | {est_minutes} | "
            f"{_escape_markdown_cell(notes_str)} | {_escape_markdown_cell(img_name)} |"
        )

    lines.append("")
    lines.append(f"**合計推定所要時間**: {total_est_minutes} 分")
    lines.append("")

    content = "\n".join(lines).rstrip() + "\n"

    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", encoding="utf-8") as f:
            f.write(content)

    return content
