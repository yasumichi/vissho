"""Pipeline orchestrator for end-to-end instruction plan generation."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict

from vissho.config import VisshoConfig
from vissho.core.validator import ValidationReport
from vissho.llm.client import LLMClientProtocol, OllamaClient
from vissho.pipeline.phase1_analyze import SlideAnalysisResult, SlideAnalyzer
from vissho.pipeline.phase2_map import SessionMapper
from vissho.pipeline.phase3_review import ConsistencyReviewer
from vissho.utils.cache import SlideCache
from vissho.utils.image import find_slide_images


class PipelineResult(BaseModel):
    """Result of the complete 3-phase pipeline execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    slide_analyses: list[SlideAnalysisResult]
    initial_plan: Any
    final_plan: Any
    validation_report: ValidationReport
    refined: bool


class PipelineOrchestrator:
    """Controls the end-to-end 3-phase pipeline: Analyze -> Map -> Review."""

    def __init__(
        self,
        config: VisshoConfig,
        client: LLMClientProtocol | None = None,
        cache: SlideCache | None = None,
        model: str | None = None,
    ) -> None:
        self.config = config
        self.client = client or OllamaClient()
        self.cache = cache or SlideCache()
        self.model = model or getattr(self.client, "default_model", OllamaClient.DEFAULT_MODEL)

        self.analyzer = SlideAnalyzer(
            config=self.config,
            client=self.client,
            cache=self.cache,
            model=self.model,
        )
        self.mapper = SessionMapper(
            config=self.config,
            client=self.client,
            model=self.model,
        )
        self.reviewer = ConsistencyReviewer(
            config=self.config,
            client=self.client,
            model=self.model,
        )

    def run(
        self,
        slides_dir: str | Path,
        pattern: str = "*.png",
        use_cache: bool = True,
        force_refine: bool = False,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> PipelineResult:
        """Execute all 3 phases sequentially.

        Args:
            slides_dir: Directory containing slide image files.
            pattern: File matching pattern for slides.
            use_cache: Whether to use cache for slide analysis.
            force_refine: Whether to force Phase 3 LLM refinement even if deterministic rules pass.
            progress_callback: Optional callback(stage_name, current_step, total_steps).
        """
        # Discover slides
        slide_items = find_slide_images(slides_dir, pattern=pattern)
        total_slides = len(slide_items)
        all_slide_numbers = [num for num, _ in slide_items]

        # Phase 1: Slide Analysis
        if progress_callback:
            progress_callback("phase1_start", 0, total_slides)

        def _phase1_progress(cur: int, tot: int, res: SlideAnalysisResult) -> None:
            if progress_callback:
                progress_callback("phase1_slide", cur, tot)

        slide_analyses = self.analyzer.analyze_images(
            slides=slide_items,
            use_cache=use_cache,
            progress_callback=_phase1_progress,
        )

        # Phase 2: Session Mapping
        total_sessions = self.config.prerequisites.total_sessions
        if progress_callback:
            progress_callback("phase2_start", 0, total_sessions)

        def _phase2_progress(cur: int, tot: int) -> None:
            if progress_callback:
                progress_callback("phase2_session", cur, tot)

        initial_plan = self.mapper.map_sessions(
            slide_analyses,
            progress_callback=_phase2_progress,
        )

        # Phase 3: Consistency Review & Refinement
        if progress_callback:
            progress_callback("phase3_start", 2, 3)

        review_result = self.reviewer.review_and_refine(
            curriculum_plan=initial_plan,
            all_slide_numbers=all_slide_numbers,
            force_refine=force_refine,
        )

        if progress_callback:
            progress_callback("complete", 3, 3)

        return PipelineResult(
            slide_analyses=slide_analyses,
            initial_plan=initial_plan,
            final_plan=review_result.curriculum_plan,
            validation_report=review_result.validation_report,
            refined=review_result.refined,
        )
