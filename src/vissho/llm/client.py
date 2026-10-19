"""Ollama client adapter and prompt rendering."""

import json
import os
from pathlib import Path
from typing import Any, Protocol
import jinja2
import ollama
from pydantic import BaseModel, Field

from vissho.config import Prerequisites

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


class LLMClientProtocol(Protocol):
    """Protocol for LLM adapters to support testing and alternate backends."""

    def analyze_slide(
        self,
        image_path: Path,
        prompt: str,
        model: str | None = None,
    ) -> SlideAnalysisOutput: ...


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


class OllamaClient:
    """Adapter for interacting with Ollama API with vision models."""

    DEFAULT_MODEL = "qwen2.5-vl"

    def __init__(
        self,
        host: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.default_model = (
            default_model or os.environ.get("VISSHO_MODEL") or self.DEFAULT_MODEL
        )
        self._client = ollama.Client(host=self.host)

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

        try:
            response = self._client.chat(
                model=target_model,
                messages=messages,
                format=schema,
            )
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
