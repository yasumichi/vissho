"""Excel exporter for curriculum plans using openpyxl.

Follows plain formatting rules (no header fill/bold for printing economy and template harmony),
applies wrap text, calculates row heights/column widths, inserts SUM formulas for session totals,
and attaches deterministic validation results.
"""

from pathlib import Path
from typing import Any
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from pydantic import BaseModel

from vissho.config import ColumnDefinition, VisshoConfig
from vissho.core.validator import ValidationReport

# Plain borders for clean grid display
_THIN_SIDE = Side(border_style="thin", color="B0B0B0")
_THIN_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)

# Standard font with no bold decoration
_PLAIN_FONT = Font(name="Yu Gothic", size=10, bold=False)
_TITLE_FONT = Font(name="Yu Gothic", size=12, bold=False)


def _calculate_row_height(
    row_data: dict[str, Any],
    columns: list[ColumnDefinition],
    min_height: float = 20.0,
    line_height: float = 16.0,
    max_height: float = 300.0,
) -> float:
    """Estimate appropriate row height based on cell text length and column width."""
    max_lines = 1
    for col in columns:
        val = row_data.get(col.name)
        if val is None:
            continue
        if isinstance(val, list):
            text = ", ".join(str(x) for x in val)
        else:
            text = str(val)

        if not text:
            continue

        col_width = col.width or 20
        cell_lines = 0
        for paragraph in text.split("\n"):
            # Approximate character width: East Asian characters count as 2, others as 1
            char_units = sum(2 if ord(c) > 127 else 1 for c in paragraph)
            needed_lines = max(1, (char_units + col_width - 1) // col_width)
            cell_lines += needed_lines

        max_lines = max(max_lines, cell_lines)

    calculated = max_lines * line_height + 4.0
    return min(max(min_height, calculated), max_height)


def export_to_excel(
    curriculum_plan: BaseModel | dict[str, Any],
    config: VisshoConfig,
    output_path: str | Path | None = None,
    validation_report: ValidationReport | None = None,
) -> Workbook:
    """Export curriculum plan to an Excel workbook (.xlsx).

    Specifications:
    - Wrap text applied to all data cells.
    - Column widths set from config metadata.
    - Row heights dynamically adjusted to prevent clipped multiline text.
    - Plain headers: NO background fill, NO bold font.
    - Excel SUM formulas for per-session duration totals.
    - Comprehensive validation report included on a dedicated sheet.

    Args:
        curriculum_plan: Curriculum plan Pydantic model or dict.
        config: Vissho configuration containing prerequisites and column definitions.
        output_path: Optional file path to write workbook.
        validation_report: Optional validation report to include.

    Returns:
        Populated openpyxl Workbook instance.
    """
    if isinstance(curriculum_plan, BaseModel):
        plan_dict = curriculum_plan.model_dump(mode="json")
    else:
        plan_dict = curriculum_plan

    wb = Workbook()

    # 1. Main Sheet: Curriculum Plan
    ws = wb.active
    ws.title = "学習指導案"
    ws.views.sheetView[0].showGridLines = True

    # Ensure allocated_minutes exists in columns for formula calculation
    columns = list(config.columns)
    col_names = [col.name for col in columns]
    if "allocated_minutes" not in col_names:
        columns.append(
            ColumnDefinition(
                name="allocated_minutes",
                description="配当時間（分）",
                width=12,
            )
        )
        col_names.append("allocated_minutes")

    allocated_col_idx = col_names.index("allocated_minutes") + 1
    allocated_col_letter = get_column_letter(allocated_col_idx)

    current_row = 1

    # Course Metadata Header
    ws.cell(
        row=current_row,
        column=1,
        value=f"【学習指導案】 {config.prerequisites.purpose}",
    ).font = _TITLE_FONT
    current_row += 1

    prereq_info = (
        f"対象者: {config.prerequisites.target_audience}  |  "
        f"前提知識: {config.prerequisites.prerequisite_knowledge or '特になし'}"
    )
    ws.cell(row=current_row, column=1, value=prereq_info).font = _PLAIN_FONT
    current_row += 1

    time_info = (
        f"コマ数: 全{config.prerequisites.total_sessions}コマ  |  "
        f"1コマ時間: {config.prerequisites.session_minutes}分  |  "
        f"総配当時間: {config.prerequisites.total_minutes}分"
    )
    ws.cell(row=current_row, column=1, value=time_info).font = _PLAIN_FONT
    current_row += 2  # Leave an empty row

    sessions = plan_dict.get("sessions", [])
    session_total_cells: list[str] = []

    # Render each session table
    for session in sessions:
        s_num = session.get("session_number", 1)
        s_title = session.get("session_title", "")
        target_mins = config.prerequisites.session_minutes

        # Session section title
        session_header_text = f"第{s_num}コマ: {s_title} (目標: {target_mins}分)"
        ws.cell(row=current_row, column=1, value=session_header_text).font = _PLAIN_FONT
        current_row += 1

        # Table Column Headers (NO fill, NO bold)
        for col_idx, col in enumerate(columns, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=col.name)
            cell.font = _PLAIN_FONT
            cell.border = _THIN_BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.row_dimensions[current_row].height = 24.0
        current_row += 1

        # Table Data Rows
        rows = session.get("rows", [])
        start_data_row = current_row

        for row_data in rows:
            for col_idx, col in enumerate(columns, start=1):
                raw_val = row_data.get(col.name)
                cell = ws.cell(row=current_row, column=col_idx)
                cell.font = _PLAIN_FONT
                cell.border = _THIN_BORDER

                if col.name == "allocated_minutes":
                    # Store as integer for Excel formula calculation
                    try:
                        cell.value = int(raw_val) if raw_val is not None else 0
                    except (ValueError, TypeError):
                        cell.value = 0
                    cell.alignment = Alignment(horizontal="right", vertical="top")
                    cell.number_format = "#,##0"
                elif isinstance(raw_val, list):
                    cell.value = ", ".join(str(x) for x in raw_val)
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                else:
                    cell.value = str(raw_val) if raw_val is not None else ""
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

            row_height = _calculate_row_height(row_data, columns)
            ws.row_dimensions[current_row].height = row_height
            current_row += 1

        end_data_row = current_row - 1

        # Session Subtotal Row (Excel SUM Formula)
        subtotal_row = current_row
        for col_idx in range(1, len(columns) + 1):
            c = ws.cell(row=subtotal_row, column=col_idx)
            c.font = _PLAIN_FONT
            c.border = _THIN_BORDER

        label_cell = ws.cell(row=subtotal_row, column=1, value=f"第{s_num}コマ 合計時間（分）")
        label_cell.alignment = Alignment(horizontal="left", vertical="center")

        sum_cell = ws.cell(row=subtotal_row, column=allocated_col_idx)
        if start_data_row <= end_data_row:
            sum_cell.value = f"=SUM({allocated_col_letter}{start_data_row}:{allocated_col_letter}{end_data_row})"
        else:
            sum_cell.value = 0
        sum_cell.alignment = Alignment(horizontal="right", vertical="center")
        sum_cell.number_format = "#,##0"

        # Record sum cell reference for grand total formula
        session_total_cells.append(f"{allocated_col_letter}{subtotal_row}")

        # Note column for target match indication
        if len(columns) > allocated_col_idx:
            note_cell = ws.cell(
                row=subtotal_row,
                column=allocated_col_idx + 1,
                value=f"目標: {target_mins}分",
            )
            note_cell.alignment = Alignment(horizontal="left", vertical="center")

        ws.row_dimensions[subtotal_row].height = 22.0
        current_row += 2  # Blank row between sessions

    # Grand Total Row
    if session_total_cells:
        grand_total_row = current_row
        for col_idx in range(1, len(columns) + 1):
            c = ws.cell(row=grand_total_row, column=col_idx)
            c.font = _PLAIN_FONT
            c.border = _THIN_BORDER

        ws.cell(row=grand_total_row, column=1, value="全コマ総合計時間（分）").alignment = (
            Alignment(horizontal="left", vertical="center")
        )
        grand_sum_cell = ws.cell(row=grand_total_row, column=allocated_col_idx)
        grand_sum_cell.value = f"={'+'.join(session_total_cells)}"
        grand_sum_cell.alignment = Alignment(horizontal="right", vertical="center")
        grand_sum_cell.number_format = "#,##0"

        if len(columns) > allocated_col_idx:
            ws.cell(
                row=grand_total_row,
                column=allocated_col_idx + 1,
                value=f"目標総時間: {config.prerequisites.total_minutes}分",
            ).alignment = Alignment(horizontal="left", vertical="center")

        ws.row_dimensions[grand_total_row].height = 24.0
        current_row += 2

    # Unassigned slides note if any
    unassigned_slides = plan_dict.get("unassigned_slides", [])
    if unassigned_slides:
        unassigned_text = f"未割り当てスライド: {', '.join(str(s) for s in unassigned_slides)}"
        ws.cell(row=current_row, column=1, value=unassigned_text).font = _PLAIN_FONT
        current_row += 2

    # Apply column widths from config metadata
    for col_idx, col in enumerate(columns, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = float(col.width or 20)

    # 2. Secondary Sheet: Validation Report (if provided)
    if validation_report is not None:
        ws_val = wb.create_sheet(title="検証結果")
        ws_val.views.sheetView[0].showGridLines = True

        v_row = 1
        ws_val.cell(row=v_row, column=1, value="【カリキュラム整合性検証レポート】").font = _TITLE_FONT
        v_row += 2

        status_text = "合格 (PASSED)" if validation_report.is_valid else "指摘事項あり (ISSUES DETECTED)"
        ws_val.cell(row=v_row, column=1, value=f"検証総合ステータス: {status_text}").font = _PLAIN_FONT
        v_row += 1

        sess_summary = (
            f"コマ数: 実際 {validation_report.total_sessions_actual} / "
            f"目標 {validation_report.total_sessions_target} "
            f"({'一致' if validation_report.total_sessions_valid else '不一致'})"
        )
        ws_val.cell(row=v_row, column=1, value=sess_summary).font = _PLAIN_FONT
        v_row += 1

        mins_summary = (
            f"総配当時間: 実際 {validation_report.total_minutes_actual}分 / "
            f"目標 {validation_report.total_minutes_target}分 "
            f"(差分: {validation_report.total_minutes_difference:+d}分)"
        )
        ws_val.cell(row=v_row, column=1, value=mins_summary).font = _PLAIN_FONT
        v_row += 2

        # Errors & Warnings list
        if validation_report.errors:
            ws_val.cell(row=v_row, column=1, value="エラー一覧:").font = _PLAIN_FONT
            v_row += 1
            for err in validation_report.errors:
                ws_val.cell(row=v_row, column=1, value=f"・{err}").font = _PLAIN_FONT
                v_row += 1
            v_row += 1

        if validation_report.warnings:
            ws_val.cell(row=v_row, column=1, value="警告一覧:").font = _PLAIN_FONT
            v_row += 1
            for warn in validation_report.warnings:
                ws_val.cell(row=v_row, column=1, value=f"・{warn}").font = _PLAIN_FONT
                v_row += 1
            v_row += 1

        # Session breakdown table
        if validation_report.session_validations:
            ws_val.cell(row=v_row, column=1, value="コマ別配当時間検証詳細:").font = _PLAIN_FONT
            v_row += 1

            val_headers = ["コマ番号", "単元・テーマ", "配当時間（分）", "目標時間（分）", "差分（分）", "判定"]
            for col_i, h in enumerate(val_headers, start=1):
                c = ws_val.cell(row=v_row, column=col_i, value=h)
                c.font = _PLAIN_FONT
                c.border = _THIN_BORDER
                c.alignment = Alignment(horizontal="center", vertical="center")
            ws_val.row_dimensions[v_row].height = 22.0
            v_row += 1

            for sv in validation_report.session_validations:
                row_vals = [
                    f"第{sv.session_number}コマ",
                    sv.session_title,
                    sv.allocated_minutes,
                    sv.target_minutes,
                    sv.difference,
                    "OK" if sv.is_valid else "差分あり",
                ]
                for col_i, val in enumerate(row_vals, start=1):
                    c = ws_val.cell(row=v_row, column=col_i, value=val)
                    c.font = _PLAIN_FONT
                    c.border = _THIN_BORDER
                    if col_i in (3, 4, 5):
                        c.alignment = Alignment(horizontal="right", vertical="center")
                        c.number_format = "#,##0"
                    elif col_i in (1, 6):
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        c.alignment = Alignment(horizontal="left", vertical="center")
                ws_val.row_dimensions[v_row].height = 20.0
                v_row += 1
            v_row += 2

        # Slide coverage breakdown
        ws_val.cell(
            row=v_row,
            column=1,
            value=f"参照スライド一覧: {', '.join(str(s) for s in validation_report.referenced_slides)}",
        ).font = _PLAIN_FONT
        v_row += 1

        if validation_report.unassigned_slides:
            ws_val.cell(
                row=v_row,
                column=1,
                value=f"未割り当てスライド: {', '.join(str(s) for s in validation_report.unassigned_slides)}",
            ).font = _PLAIN_FONT
            v_row += 1

        if validation_report.missing_slides:
            ws_val.cell(
                row=v_row,
                column=1,
                value=f"未言及（欠落）スライド: {', '.join(str(s) for s in validation_report.missing_slides)}",
            ).font = _PLAIN_FONT
            v_row += 1

        if validation_report.invalid_slide_references:
            ws_val.cell(
                row=v_row,
                column=1,
                value=f"不正なスライド参照: {', '.join(str(s) for s in validation_report.invalid_slide_references)}",
            ).font = _PLAIN_FONT
            v_row += 1

        # Adjust column widths on validation sheet
        val_widths = [14, 30, 16, 16, 14, 14]
        for col_i, w in enumerate(val_widths, start=1):
            ws_val.column_dimensions[get_column_letter(col_i)].width = float(w)

    # Save to file if output_path specified
    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target_path)

    return wb


def export_slide_analyses_to_excel(
    slide_analyses: list[Any],
    output_path: str | Path | None = None,
    title: str = "スライド解析結果一覧",
) -> Workbook:
    """Export Phase 1 individual slide analysis results to an Excel workbook.

    Follows plain design principles: Yu Gothic 10pt, no header bold/fill,
    wrap text, automatic column widths and row heights, and a SUM formula
    for total estimated minutes.

    Args:
        slide_analyses: List of SlideAnalysisResult instances or dictionaries.
        output_path: Optional path to save the generated workbook (.xlsx).
        title: Title placed in the header block.

    Returns:
        The openpyxl Workbook object.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "スライド解析一覧"
    ws.views.sheetView[0].showGridLines = True

    # Title block
    ws.cell(row=1, column=1, value=f"【{title}】").font = _TITLE_FONT
    ws.cell(row=2, column=1, value=f"対象スライド数: {len(slide_analyses)} 枚").font = _PLAIN_FONT

    # Header definition
    headers = [
        ("スライド番号", 12, "center"),
        ("タイトル", 26, "left"),
        ("主なトピック", 28, "left"),
        ("重要ポイント", 35, "left"),
        ("想定学習活動", 28, "left"),
        ("目安時間（分）", 14, "right"),
        ("指導上の留意点・暗黙知", 35, "left"),
        ("画像ファイル", 20, "left"),
    ]

    header_row = 4
    ws.row_dimensions[header_row].height = 24.0

    for col_idx, (col_name, col_width, align) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=col_name)
        cell.font = _PLAIN_FONT
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = float(col_width)

    current_row = header_row + 1
    data_start_row = current_row

    for item in slide_analyses:
        if isinstance(item, BaseModel):
            item_dict = item.model_dump(mode="python")
        elif isinstance(item, dict):
            item_dict = item
        else:
            item_dict = {"slide_number": getattr(item, "slide_number", 0)}

        analysis = item_dict.get("analysis", {})
        if isinstance(analysis, BaseModel):
            analysis = analysis.model_dump(mode="python")

        slide_num = item_dict.get("slide_number", 0)
        slide_title = analysis.get("title", "")
        topics = ", ".join(analysis.get("topics", []))
        key_points = "\n".join(f"・{p}" for p in analysis.get("key_points", []))
        activities = ", ".join(analysis.get("suggested_activities", []))
        est_minutes = analysis.get("estimated_minutes", 0)

        # Merge instructor notes and supplementary notes
        all_notes: list[str] = []
        if analysis.get("instructor_notes"):
            all_notes.extend(analysis["instructor_notes"])
        if item_dict.get("supplementary_notes"):
            all_notes.extend(item_dict["supplementary_notes"])
        notes_str = "\n".join(f"・{n}" for n in all_notes) if all_notes else ""

        raw_path = item_dict.get("image_path", "")
        img_name = Path(raw_path).name if raw_path else ""

        row_values = [
            slide_num,
            slide_title,
            topics,
            key_points,
            activities,
            est_minutes,
            notes_str,
            img_name,
        ]

        # Calculate row height based on text content
        max_lines = 1
        for val, (col_name, col_width, _) in zip(row_values, headers, strict=False):
            text = str(val or "")
            if not text:
                continue
            col_lines = 0
            for paragraph in text.split("\n"):
                char_units = sum(2 if ord(c) > 127 else 1 for c in paragraph)
                needed = max(1, (char_units + col_width - 1) // col_width)
                col_lines += needed
            max_lines = max(max_lines, col_lines)

        row_h = min(max(20.0, max_lines * 16.0 + 4.0), 300.0)
        ws.row_dimensions[current_row].height = row_h

        for col_idx, (val, (_, _, align)) in enumerate(zip(row_values, headers, strict=False), start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _PLAIN_FONT
            cell.border = _THIN_BORDER
            cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
            if col_idx == 6:  # estimated_minutes
                cell.number_format = "#,##0"

        current_row += 1

    data_end_row = current_row - 1

    # Total row if there is at least one data row
    if data_end_row >= data_start_row:
        total_row = current_row
        ws.row_dimensions[total_row].height = 24.0

        for col_idx in range(1, len(headers) + 1):
            c = ws.cell(row=total_row, column=col_idx)
            c.font = _PLAIN_FONT
            c.border = _THIN_BORDER

        label_cell = ws.cell(row=total_row, column=1, value="合計目安時間")
        label_cell.alignment = Alignment(horizontal="center", vertical="center")

        sum_cell = ws.cell(row=total_row, column=6)
        sum_cell.value = f"=SUM(F{data_start_row}:F{data_end_row})"
        sum_cell.number_format = "#,##0"
        sum_cell.alignment = Alignment(horizontal="right", vertical="center")

    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target_path)

    return wb
