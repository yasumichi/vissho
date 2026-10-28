"""Ollama client adapter and prompt rendering."""

import json
import os
from pathlib import Path
from typing import Any, Protocol
import jinja2
import ollama
from pydantic import BaseModel, Field

from vissho.config import ColumnDefinition, Prerequisites

PROMPTS_DIR = Path(__file__).parent / "prompts"


class SlideAnalysisOutput(BaseModel):
    """Structured extraction of elements from a single slide."""

    title: str = Field(..., description="スライドのタイトルまたは主題")
    topics: list[str] = Field(default_factory=list, description="扱われている主な概念やキーワード")
    key_points: list[str] = Field(
        default_factory=list, description="スライドの説明内容・重要ポイント（要約）"
    )
    suggested_activities: list[str] = Field(
        default_factory=list,
        description="想定される学習活動（解説、演習、質疑応答など）",
    )
    estimated_minutes: int = Field(
        default=5, ge=1, description="このスライドを用いた指導にかける想定時間（分）"
    )
    instructor_notes: list[str] = Field(
        default_factory=list, description="指導上の留意点、受講生のつまずきポイント、暗黙知"
    )


class SlideSummaryItem(BaseModel):
    """Lightweight summary of a slide for Step 2-A course outline mapping."""

    slide_number: int = Field(..., description="スライド番号")
    title: str = Field(..., description="スライドのタイトルまたは主題")
    topics: list[str] = Field(default_factory=list, description="主な概念やキーワード")
    estimated_minutes: int = Field(default=5, ge=1, description="所要目安時間（分）")
    has_notes: bool = Field(default=False, description="補足・暗黙知メモの有無")


class LLMClientProtocol(Protocol):
    """Protocol for LLM adapters to support testing and alternate backends."""

    def analyze_slide(
        self,
        image_path: Path,
        prompt: str,
        model: str | None = None,
    ) -> SlideAnalysisOutput: ...

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any],
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]: ...


def get_prompt_environment() -> jinja2.Environment:
    """Create a Jinja2 template environment for prompt rendering."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_slide_analysis_prompt(
    prerequisites: Prerequisites,
    slide_number: int,
    supplementary_notes: list[str] | None = None,
) -> str:
    """Render the Jinja2 prompt template for slide analysis."""
    env = get_prompt_environment()
    template = env.get_template("slide_analysis.j2")
    return template.render(
        prerequisites=prerequisites,
        slide_number=slide_number,
        supplementary_notes=supplementary_notes or [],
    )


def render_session_mapping_prompt(
    prerequisites: Prerequisites,
    columns: list[ColumnDefinition],
    slide_analyses: list[Any],
) -> str:
    """Render the Jinja2 prompt template for legacy session mapping."""
    env = get_prompt_environment()
    template = env.get_template("session_mapping.j2")
    return template.render(
        prerequisites=prerequisites,
        columns=columns,
        slide_analyses=slide_analyses,
    )


def render_course_outline_prompt(
    prerequisites: Prerequisites,
    slide_summaries: list[SlideSummaryItem | dict[str, Any]],
) -> str:
    """Render the Jinja2 prompt template for Step 2-A course outline mapping."""
    env = get_prompt_environment()
    template = env.get_template("course_outline.j2")
    return template.render(
        prerequisites=prerequisites,
        slide_summaries=slide_summaries,
    )


def render_session_detail_prompt(
    prerequisites: Prerequisites,
    session_number: int,
    session_title: str,
    columns: list[ColumnDefinition],
    slide_analyses: list[Any],
) -> str:
    """Render the Jinja2 prompt template for Step 2-B single session detail generation."""
    env = get_prompt_environment()
    template = env.get_template("session_detail.j2")
    return template.render(
        prerequisites=prerequisites,
        session_number=session_number,
        session_title=session_title,
        columns=columns,
        slide_analyses=slide_analyses,
    )


def render_consistency_review_prompt(
    prerequisites: Prerequisites,
    columns: list[ColumnDefinition],
    curriculum_plan: Any,
    validation_report: Any,
) -> str:
    """Render the Jinja2 prompt template for consistency review and refinement."""
    env = get_prompt_environment()
    template = env.get_template("consistency_review.j2")

    # If curriculum_plan is a Pydantic model, convert to dict for template access
    if isinstance(curriculum_plan, BaseModel):
        plan_dict = curriculum_plan.model_dump(mode="json")
    elif isinstance(curriculum_plan, dict):
        plan_dict = curriculum_plan
    else:
        plan_dict = {"sessions": getattr(curriculum_plan, "sessions", []), "unassigned_slides": getattr(curriculum_plan, "unassigned_slides", [])}

    return template.render(
        prerequisites=prerequisites,
        columns=columns,
        curriculum_plan=plan_dict,
        validation_report=validation_report,
    )


class OllamaClient:
    """Adapter for interacting with Ollama API with vision models."""

    DEFAULT_MODEL = "qwen2.5-vl"

    def __init__(
        self,
        host: str | None = None,
        default_model: str | None = None,
        num_ctx: int | None = None,
    ) -> None:
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.default_model = (
            default_model or os.environ.get("VISSHO_MODEL") or self.DEFAULT_MODEL
        )
        ctx_env = os.environ.get("VISSHO_NUM_CTX")
        self.num_ctx = num_ctx if num_ctx is not None else (int(ctx_env) if ctx_env else None)
        self._client = ollama.Client(host=self.host)

    def _get_options(self) -> dict[str, Any] | None:
        """Construct Ollama options dictionary if configured."""
        if self.num_ctx is not None:
            return {"num_ctx": self.num_ctx}
        return None

    def analyze_slide(
        self,
        image_path: Path,
        prompt: str,
        model: str | None = None,
    ) -> SlideAnalysisOutput:
        """Call Ollama vision model to analyze a slide image with structured JSON output."""
        target_model = model or self.default_model

        if not image_path.is_file():
            raise FileNotFoundError(f"Slide image not found: {image_path}")

        schema = SlideAnalysisOutput.model_json_schema()

        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [str(image_path)],
            }
        ]

        chat_kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "format": schema,
        }
        options = self._get_options()
        if options:
            chat_kwargs["options"] = options

        try:
            response = self._client.chat(**chat_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to call Ollama model '{target_model}' at {self.host}: {e}"
            ) from e

        content = response["message"]["content"]
        try:
            parsed = json.loads(content)
            return SlideAnalysisOutput.model_validate(parsed)
        except Exception as e:
            raise ValueError(
                f"Failed to parse structured output from Ollama response: {e}\nRaw content: {content}"
            ) from e

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any],
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Call Ollama model to generate structured JSON output following the given schema."""
        target_model = model or self.default_model

        if isinstance(schema, dict):
            schema_dict = schema
        else:
            schema_dict = schema.model_json_schema()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        chat_kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "format": schema_dict,
        }
        options = self._get_options()
        if options:
            chat_kwargs["options"] = options

        try:
            response = self._client.chat(**chat_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to call Ollama model '{target_model}' at {self.host}: {e}"
            ) from e

        content = response["message"]["content"]
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object from Ollama, got: {type(parsed)}")
            return parsed
        except Exception as e:
            raise ValueError(
                f"Failed to parse structured output from Ollama response: {e}\nRaw content: {content}"
            ) from e
