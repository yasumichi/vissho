"""Tests for slide caching."""

from pathlib import Path
from pydantic import BaseModel

from vissho.utils.cache import SlideCache


class DummyResult(BaseModel):
    title: str
    minutes: int


def test_cache_miss_and_hit(tmp_path: Path) -> None:
    cache = SlideCache(cache_dir=tmp_path / ".vissho_cache")
    image_hash = "abcdef1234567890"
    model = "qwen2.5-vl"

    # Initially cache miss
    assert cache.get(image_hash, model) is None

    # Save to cache
    payload = {"title": "Introduction", "minutes": 10}
    cache.set(image_hash, model, payload)

    # Cache hit
    cached = cache.get(image_hash, model)
    assert cached is not None
    assert cached["image_hash"] == image_hash
    assert cached["model"] == model
    assert cached["payload"] == payload


def test_cache_with_pydantic_model(tmp_path: Path) -> None:
    cache = SlideCache(cache_dir=tmp_path / ".vissho_cache")
    image_hash = "hash999"
    model = "llava"

    item = DummyResult(title="Test Pydantic", minutes=15)
    cache.set(image_hash, model, item)

    cached = cache.get(image_hash, model)
    assert cached is not None
    assert cached["payload"]["title"] == "Test Pydantic"
    assert cached["payload"]["minutes"] == 15


def test_cache_key_changes_with_notes(tmp_path: Path) -> None:
    cache = SlideCache(cache_dir=tmp_path / ".vissho_cache")
    image_hash = "same_hash"
    model = "model_a"

    cache.set(image_hash, model, {"key": "without_note"}, supplementary_notes=None)
    cache.set(image_hash, model, {"key": "with_note"}, supplementary_notes=["Teacher Note"])

    res_without = cache.get(image_hash, model, supplementary_notes=None)
    res_with = cache.get(image_hash, model, supplementary_notes=["Teacher Note"])

    assert res_without is not None and res_without["payload"]["key"] == "without_note"
    assert res_with is not None and res_with["payload"]["key"] == "with_note"


def test_cache_clear(tmp_path: Path) -> None:
    cache = SlideCache(cache_dir=tmp_path / ".vissho_cache")
    cache.set("hash1", "model", {"data": 1})
    cache.set("hash2", "model", {"data": 2})

    assert cache.get("hash1", "model") is not None
    deleted = cache.clear()
    assert deleted == 2
    assert cache.get("hash1", "model") is None
