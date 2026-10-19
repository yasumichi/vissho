"""Image handling and slide number extraction utilities."""

import hashlib
import re
from pathlib import Path
from PIL import Image


def extract_slide_number(file_path: str | Path) -> int:
    """Extract the slide number from an image file name.

    According to the spec, the slide number is located at the end of the file stem
    (e.g., 'slide_01.png' -> 1, '01.png' -> 1, 'lecture-page-12.png' -> 12).

    Raises:
        ValueError: If no slide number could be extracted from the file name.
    """
    path = Path(file_path)
    stem = path.stem

    # Match the last sequence of digits in the file stem
    match = re.search(r"(\d+)(?!.*\d)", stem)
    if not match:
        raise ValueError(
            f"Could not extract slide number from file name: '{path.name}'. "
            "File name must contain a slide number (e.g., slide_01.png, 01.png)."
        )

    return int(match.group(1))


def compute_image_hash(file_path: str | Path) -> str:
    """Calculate the SHA256 hash of an image file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)

    return hasher.hexdigest()


def validate_image_file(file_path: str | Path) -> bool:
    """Verify that the file exists and is a valid image file.

    Returns:
        True if the file can be opened as an image, False otherwise.
    """
    path = Path(file_path)
    if not path.is_file():
        return False

    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def find_slide_images(
    directory: str | Path,
    pattern: str = "*.png",
) -> list[tuple[int, Path]]:
    """Scan a directory for slide images matching the pattern and sort by slide number.

    Returns:
        List of tuples: (slide_number, file_path), sorted ascending by slide_number.

    Raises:
        FileNotFoundError: If the directory does not exist.
        ValueError: If no valid slide images were found or if duplicate slide numbers exist.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Slide images directory not found: {dir_path}")

    slide_images: list[tuple[int, Path]] = []
    seen_numbers: dict[int, Path] = {}

    for file_path in dir_path.glob(pattern):
        if not file_path.is_file():
            continue
        try:
            num = extract_slide_number(file_path)
        except ValueError:
            continue

        if num in seen_numbers:
            raise ValueError(
                f"Duplicate slide number {num} found in '{file_path.name}' "
                f"and '{seen_numbers[num].name}'."
            )

        seen_numbers[num] = file_path
        slide_images.append((num, file_path))

    if not slide_images:
        raise ValueError(
            f"No slide images matching '{pattern}' with valid slide numbers found in: {dir_path}"
        )

    slide_images.sort(key=lambda x: x[0])
    return slide_images
