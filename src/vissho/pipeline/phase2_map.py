"""Phase 2: Session mapper engine for structuring slide elements into curriculum sessions using 2-step mapping."""

from collections.abc import Callable
from typing import Any
from pydantic import BaseModel

from vissho.config import VisshoConfig
from vissho.core.schema import (
    CourseOutline,
    SessionOutline,
    create_curriculum_plan_model,
    create_instruction_row_model,
    create_session_plan_model,
)
from vissho.llm.client import (
    LLMClientProtocol,
    OllamaClient,
    SlideSummaryItem,
    render_course_outline_prompt,
    render_session_detail_prompt,
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
        self.row_model = create_instruction_row_model(self.config.columns)
        self.session_model = create_session_plan_model(self.row_model)
        self.curriculum_model = create_curriculum_plan_model(self.config.columns)

    def map_sessions(
        self,
        slide_analyses: list[SlideAnalysisResult],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BaseModel:
        """Map slide analysis results into structured class sessions using 2-step mapping.

        Step 2-A: Generate high-level course outline allocating slides to sessions.
        Step 2-B: Generate detailed instruction plan rows for each session independently.

        Args:
            slide_analyses: Analysis results from Phase 1.
            progress_callback: Optional callback(current_session, total_sessions) for progress reporting.

        Returns:
            An instance of the dynamically generated CurriculumPlan model.

        Raises:
            ValueError: If slide_analyses is empty or if structured generation fails.
        """
        if not slide_analyses:
            raise ValueError("Cannot map empty slide analysis results to class sessions.")

        # Ensure slides are ordered by slide_number
        sorted_slides = sorted(slide_analyses, key=lambda s: s.slide_number)
        slide_dict = {s.slide_number: s for s in sorted_slides}
        all_slide_numbers = set(slide_dict.keys())
        total_sessions = self.config.prerequisites.total_sessions

        # -------------------------------------------------------------
        # Step 2-A: Course Outline Mapping (Global allocation)
        # -------------------------------------------------------------
        summaries = [
            SlideSummaryItem(
                slide_number=s.slide_number,
                title=s.analysis.title,
                topics=s.analysis.topics,
                estimated_minutes=s.analysis.estimated_minutes,
                has_notes=bool(s.supplementary_notes or s.analysis.instructor_notes),
            )
            for s in sorted_slides
        ]

        outline_prompt = render_course_outline_prompt(
            prerequisites=self.config.prerequisites,
            slide_summaries=summaries,
        )

        raw_outline = self.client.generate_structured(
            prompt=outline_prompt,
            schema=CourseOutline,
            model=self.model,
        )
        course_outline = CourseOutline.model_validate(raw_outline)

        # Normalize and safeguard session outline
        assigned_slides: set[int] = set()
        validated_sessions: list[SessionOutline] = []
        existing_by_num = {s.session_number: s for s in course_outline.sessions}

        for s_idx in range(1, total_sessions + 1):
            if s_idx in existing_by_num:
                s_outline = existing_by_num[s_idx]
            elif s_idx - 1 < len(course_outline.sessions):
                s_outline = course_outline.sessions[s_idx - 1]
            else:
                s_outline = SessionOutline(
                    session_number=s_idx,
                    session_title=f"第{s_idx}コマ",
                    slide_numbers=[],
                )

            valid_nums: list[int] = []
            for num in s_outline.slide_numbers:
                if num in all_slide_numbers and num not in assigned_slides:
                    valid_nums.append(num)
                    assigned_slides.add(num)

            validated_sessions.append(
                SessionOutline(
                    session_number=s_idx,
                    session_title=s_outline.session_title or f"第{s_idx}コマ",
                    slide_numbers=valid_nums,
                )
            )

        # Collect unassigned slides
        unassigned = [
            num
            for num in course_outline.unassigned_slides
            if num in all_slide_numbers and num not in assigned_slides
        ]
        remaining = [
            num
            for num in sorted(all_slide_numbers)
            if num not in assigned_slides and num not in unassigned
        ]
        unassigned.extend(remaining)
        unassigned.sort()

        # -------------------------------------------------------------
        # Step 2-B: Single Session Detail Generation (Per session)
        # -------------------------------------------------------------
        sessions_plan: list[BaseModel] = []
        for idx, s_outline in enumerate(validated_sessions):
            if progress_callback:
                progress_callback(idx + 1, total_sessions)

            session_slides = [
                slide_dict[num] for num in s_outline.slide_numbers if num in slide_dict
            ]

            detail_prompt = render_session_detail_prompt(
                prerequisites=self.config.prerequisites,
                session_number=s_outline.session_number,
                session_title=s_outline.session_title,
                columns=self.config.columns,
                slide_analyses=session_slides,
            )

            raw_session = self.client.generate_structured(
                prompt=detail_prompt,
                schema=self.session_model,
                model=self.model,
            )
            session_plan = self.session_model.model_validate(raw_session)

            # Ensure session identity
            session_plan.session_number = s_outline.session_number
            if not getattr(session_plan, "session_title", None):
                setattr(session_plan, "session_title", s_outline.session_title)

            # Recalculate total_minutes from actual rows
            calculated_total = 0
            for row in getattr(session_plan, "rows", []):
                allocated = getattr(row, "allocated_minutes", 0)
                if isinstance(allocated, int):
                    calculated_total += allocated

            setattr(session_plan, "total_minutes", calculated_total)
            sessions_plan.append(session_plan)

        # -------------------------------------------------------------
        # Merge into final CurriculumPlan
        # -------------------------------------------------------------
        plan_dict = {
            "sessions": [
                s.model_dump(mode="python") if isinstance(s, BaseModel) else s
                for s in sessions_plan
            ],
            "unassigned_slides": unassigned,
        }
        return self.curriculum_model.model_validate(plan_dict)
