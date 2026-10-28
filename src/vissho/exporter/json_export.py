"""JSON exporter for curriculum plans, supporting secondary processing and web integrations."""

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel

from vissho.config import VisshoConfig
from vissho.core.validator import ValidationReport


def export_to_json(
    curriculum_plan: BaseModel | dict[str, Any],
    output_path: str | Path | None = None,
    config: VisshoConfig | None = None,
    validation_report: ValidationReport | None = None,
    include_metadata: bool = False,
    indent: int = 2,
) -> str:
    """Export curriculum plan to a JSON formatted string and optionally save to file.

    Args:
        curriculum_plan: Curriculum plan Pydantic model or dict.
        output_path: Optional file path to write JSON.
        config: Optional configuration object to include metadata.
        validation_report: Optional validation report to include.
        include_metadata: Whether to wrap the plan in a metadata structure containing
                          prerequisites, column definitions, and validation results.
        indent: Indentation level for JSON formatting.

    Returns:
        Formatted JSON string.
    """
    if isinstance(curriculum_plan, BaseModel):
        plan_dict = curriculum_plan.model_dump(mode="json")
    else:
        plan_dict = curriculum_plan

    if include_metadata:
        payload: dict[str, Any] = {
            "version": "1.0",
            "plan": plan_dict,
        }
        if config is not None:
            payload["prerequisites"] = config.prerequisites.model_dump(mode="json")
            payload["columns"] = [col.model_dump(mode="json") for col in config.columns]
        if validation_report is not None:
            payload["validation"] = validation_report.model_dump(mode="json")
    else:
        payload = plan_dict

    json_str = json.dumps(payload, ensure_ascii=False, indent=indent)

    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", encoding="utf-8") as f:
            f.write(json_str)

    return json_str


def export_slide_analyses_to_json(
    slide_analyses: list[Any],
    output_path: str | Path | None = None,
    indent: int = 2,
) -> str:
    """Export Phase 1 slide analysis results to a JSON formatted string and optionally save to file.

    Args:
        slide_analyses: List of SlideAnalysisResult instances or dictionaries.
        output_path: Optional file path to write JSON.
        indent: Indentation level for JSON formatting.

    Returns:
        Formatted JSON string.
    """
    items: list[dict[str, Any]] = []
    for item in slide_analyses:
        if isinstance(item, BaseModel):
            items.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            items.append(item)
        else:
            items.append({"slide_number": getattr(item, "slide_number", 0)})

    json_str = json.dumps(items, ensure_ascii=False, indent=indent)

    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", encoding="utf-8") as f:
            f.write(json_str)

    return json_str
