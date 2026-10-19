"""Cache manager for slide analysis results."""

import hashlib
import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel


class SlideCache:
    """Manages disk caching of slide analysis results to avoid redundant LLM inferences."""

    def __init__(self, cache_dir: str | Path = ".vissho_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.slides_dir = self.cache_dir / "slides"

    def _ensure_dir(self) -> None:
        self.slides_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_cache_key(
        image_hash: str,
        model: str,
        supplementary_notes: list[str] | None = None,
    ) -> str:
        """Generate a deterministic cache key.

        The key is based on the image SHA256 hash, the LLM model identifier,
        and any supplementary notes injected for this slide.
        """
        notes = supplementary_notes or []
        serialized_notes = "\n".join(sorted(notes))
        raw_key = f"{image_hash}::{model}::{serialized_notes}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get_cache_path(self, cache_key: str) -> Path:
        """Return the file path for the given cache key."""
        return self.slides_dir / f"{cache_key}.json"

    def get(
        self,
        image_hash: str,
        model: str,
        supplementary_notes: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve cached analysis data if available."""
        key = self.compute_cache_key(image_hash, model, supplementary_notes)
        cache_file = self.get_cache_path(key)

        if not cache_file.is_file():
            return None

        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            return None
        except Exception:
            # Corrupted cache file, ignore and return None
            return None

    def set(
        self,
        image_hash: str,
        model: str,
        data: dict[str, Any] | BaseModel,
        supplementary_notes: list[str] | None = None,
    ) -> None:
        """Save analysis data to cache."""
        self._ensure_dir()
        key = self.compute_cache_key(image_hash, model, supplementary_notes)
        cache_file = self.get_cache_path(key)

        if isinstance(data, BaseModel):
            payload = data.model_dump(mode="json")
        else:
            payload = data

        cache_metadata = {
            "cache_key": key,
            "image_hash": image_hash,
            "model": model,
            "supplementary_notes": supplementary_notes or [],
            "payload": payload,
        }

        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(cache_metadata, f, ensure_ascii=False, indent=2)

    def clear(self) -> int:
        """Clear all cached slide analysis files and return the number of deleted files."""
        if not self.slides_dir.exists():
            return 0

        count = 0
        for cache_file in self.slides_dir.glob("*.json"):
            if cache_file.is_file():
                cache_file.unlink()
                count += 1
        return count
