"""Phase 1: Individual slide analyzer engine."""

from collections.abc import Callable
from pathlib import Path
from pydantic import BaseModel, Field

from vissho.config import VisshoConfig
from vissho.llm.client import (
    LLMClientProtocol,
    OllamaClient,
    SlideAnalysisOutput,
    render_slide_analysis_prompt,
)
from vissho.utils.cache import SlideCache
from vissho.utils.image import compute_image_hash, find_slide_images


class SlideAnalysisResult(BaseModel):
    """Encapsulates the complete analysis result for a single slide, including provenance."""

    slide_number: int = Field(..., ge=1, description="スライド番号 (1-indexed)")
    image_path: str = Field(..., description="スライド画像ファイルのパス")
    image_hash: str = Field(..., description="スライド画像のSHA256ハッシュ")
    analysis: SlideAnalysisOutput = Field(..., description="LLMによる構造化解析データ")
    supplementary_notes: list[str] = Field(
        default_factory=list, description="適用された担当教員からの補足・暗黙知メモ"
    )
    cached: bool = Field(
        default=False, description="キャッシュから取得された結果かどうか"
    )


class SlideAnalyzer:
    """Analyzer engine for Phase 1: extracting instructional concepts from individual slides."""

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

    def analyze_slide(
        self,
        slide_number: int,
        image_path: str | Path,
        use_cache: bool = True,
    ) -> SlideAnalysisResult:
        """Analyze a single slide image, utilizing cache if available."""
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Slide image not found: {path}")

        image_hash = compute_image_hash(path)
        notes = self.config.get_notes_for_slide(slide_number)

        # 1. Check cache
        if use_cache:
            cached_data = self.cache.get(
                image_hash=image_hash,
                model=self.model,
                supplementary_notes=notes,
            )
            if cached_data and "payload" in cached_data:
                try:
                    analysis_output = SlideAnalysisOutput.model_validate(
                        cached_data["payload"]
                    )
                    return SlideAnalysisResult(
                        slide_number=slide_number,
                        image_path=str(path.resolve()),
                        image_hash=image_hash,
                        analysis=analysis_output,
                        supplementary_notes=notes,
                        cached=True,
                    )
                except Exception:
                    # Ignore corrupted cached payload and re-analyze
                    pass

        # 2. Render prompt and call LLM
        prompt = render_slide_analysis_prompt(
            prerequisites=self.config.prerequisites,
            slide_number=slide_number,
            supplementary_notes=notes,
        )

        analysis_output = self.client.analyze_slide(
            image_path=path,
            prompt=prompt,
            model=self.model,
        )

        # 3. Store in cache
        if use_cache:
            self.cache.set(
                image_hash=image_hash,
                model=self.model,
                data=analysis_output,
                supplementary_notes=notes,
            )

        return SlideAnalysisResult(
            slide_number=slide_number,
            image_path=str(path.resolve()),
            image_hash=image_hash,
            analysis=analysis_output,
            supplementary_notes=notes,
            cached=False,
        )

    def analyze_images(
        self,
        slides: list[tuple[int, Path]],
        use_cache: bool = True,
        progress_callback: Callable[[int, int, SlideAnalysisResult], None] | None = None,
    ) -> list[SlideAnalysisResult]:
        """Analyze a list of (slide_number, file_path) pairs sequentially."""
        results: list[SlideAnalysisResult] = []
        total = len(slides)

        for idx, (num, path) in enumerate(slides, start=1):
            result = self.analyze_slide(
                slide_number=num,
                image_path=path,
                use_cache=use_cache,
            )
            results.append(result)
            if progress_callback:
                progress_callback(idx, total, result)

        return results

    def analyze_directory(
        self,
        directory: str | Path,
        pattern: str = "*.png",
        use_cache: bool = True,
        progress_callback: Callable[[int, int, SlideAnalysisResult], None] | None = None,
    ) -> list[SlideAnalysisResult]:
        """Discover slide images in directory, sorted by slide number, and analyze all of them."""
        slides = find_slide_images(directory, pattern=pattern)
        return self.analyze_images(
            slides=slides,
            use_cache=use_cache,
            progress_callback=progress_callback,
        )
