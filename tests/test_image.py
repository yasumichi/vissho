"""Tests for image utilities."""

import pytest
from pathlib import Path
from PIL import Image

from vissho.utils.image import (
    extract_slide_number,
    compute_image_hash,
    validate_image_file,
    find_slide_images,
)


def _create_dummy_png(path: Path, color: str = "blue") -> None:
    img = Image.new("RGB", (32, 32), color=color)
    img.save(path, format="PNG")


def test_extract_slide_number_success() -> None:
    assert extract_slide_number("slide_01.png") == 1
    assert extract_slide_number("slide_10.png") == 10
    assert extract_slide_number("01.png") == 1
    assert extract_slide_number("lecture-page-12.png") == 12
    assert extract_slide_number("slide_part2_05.png") == 5
    assert extract_slide_number(Path("/tmp/presentation/003.png")) == 3


def test_extract_slide_number_failure() -> None:
    with pytest.raises(ValueError, match="Could not extract slide number"):
        extract_slide_number("cover.png")

    with pytest.raises(ValueError, match="Could not extract slide number"):
        extract_slide_number("presentation.png")


def test_compute_image_hash(tmp_path: Path) -> None:
    img_path = tmp_path / "test.png"
    _create_dummy_png(img_path, color="red")

    hash1 = compute_image_hash(img_path)
    assert len(hash1) == 64  # SHA256 hex string

    # Same content -> same hash
    hash2 = compute_image_hash(img_path)
    assert hash1 == hash2

    # Different content -> different hash
    img_path2 = tmp_path / "test2.png"
    _create_dummy_png(img_path2, color="green")
    assert compute_image_hash(img_path2) != hash1


def test_validate_image_file(tmp_path: Path) -> None:
    valid_png = tmp_path / "valid.png"
    _create_dummy_png(valid_png)
    assert validate_image_file(valid_png) is True

    invalid_file = tmp_path / "corrupt.png"
    invalid_file.write_bytes(b"not an image")
    assert validate_image_file(invalid_file) is False

    non_existent = tmp_path / "missing.png"
    assert validate_image_file(non_existent) is False


def test_find_slide_images(tmp_path: Path) -> None:
    _create_dummy_png(tmp_path / "slide_03.png")
    _create_dummy_png(tmp_path / "slide_01.png")
    _create_dummy_png(tmp_path / "slide_02.png")
    _create_dummy_png(tmp_path / "unrelated.txt")

    slides = find_slide_images(tmp_path)
    assert len(slides) == 3
    assert [num for num, _ in slides] == [1, 2, 3]
    assert [p.name for _, p in slides] == ["slide_01.png", "slide_02.png", "slide_03.png"]


def test_find_slide_images_duplicate_error(tmp_path: Path) -> None:
    _create_dummy_png(tmp_path / "slide_01.png")
    _create_dummy_png(tmp_path / "page_01.png")

    with pytest.raises(ValueError, match="Duplicate slide number 1 found"):
        find_slide_images(tmp_path)


def test_find_slide_images_empty_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No slide images matching"):
        find_slide_images(tmp_path)
