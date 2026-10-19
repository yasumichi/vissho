"""Phase 2: Session mapper engine for structuring slide elements into curriculum sessions."""

from typing import Any
from pydantic import BaseModel

from vissho.config import VisshoConfig
from vissho.core.schema import create_curriculum_plan_model
from vissho.llm.client import (
    LLMClientProtocol,
    OllamaClient,
    render_session_mapping_prompt,
)
from vissho.pipeline.phase1_analyze import SlideAnalysisResult


class SessionMapper:
    """Mapper engine for Phase 2: structuring extracted slide elements into class sessions."""

    def __init__(
        self,
        config: VisshoConfig,
        client: LLMClientProtocol | None = None,
        model: str | None = None,
    ) -> None:
        self.config = config
        self.client = client or OllamaClient()
        self.model = model or getattr(self.client, "default_model", OllamaClient.DEFAULT_MODEL)
        self.curriculum_model = create_curriculum_plan_model(self.config.columns)

    def map_sessions(
        self,
        slide_analyses: list[SlideAnalysisResult],
    ) -> BaseModel:
        """Map slide analysis results into structured class sessions according to config.

        Args:
            slide_analyses: Analysis results from Phase 1.

        Returns:
            An instance of the dynamically generated CurriculumPlan model.

        Raises:
            ValueError: If slide_analyses is empty or if structured generation fails.
        """
        if not slide_analyses:
            raise ValueError("Cannot map empty slide analysis results to class sessions.")

        # Ensure slides are ordered by slide_number
        sorted_slides = sorted(slide_analyses, key=lambda s: s.slide_number)

        # 1. Render prompt
        prompt = render_session_mapping_prompt(
            prerequisites=self.config.prerequisites,
            columns=self.config.columns,
            slide_analyses=sorted_slides,
        )

        # 2. Call LLM for structured output
        raw_data = self.client.generate_structured(
            prompt=prompt,
            schema=self.curriculum_model,
            model=self.model,
        )

        # 3. Validate against dynamic CurriculumPlan schema
        curriculum_plan = self.curriculum_model.model_validate(raw_data)

        # 4. Deterministic recalculation: ensure session total_minutes matches row allocations
        for session in getattr(curriculum_plan, "sessions", []):
            calculated_total = 0
            for row in getattr(session, "rows", []):
                allocated = getattr(row, "allocated_minutes", 0)
                if isinstance(allocated, int):
                    calculated_total += allocated
            # If total_minutes was missing or inconsistent, sync with calculated sum
            if getattr(session, "total_minutes", None) != calculated_total:
                setattr(session, "total_minutes", calculated_total)

        return curriculum_plan
