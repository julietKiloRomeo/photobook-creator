from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps


@dataclass(frozen=True)
class ThumbnailResult:
    source: Path
    size: int
    output_path: Path
    width: int
    height: int


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def iter_photo_paths(paths: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    for entry in paths:
        if entry.is_dir():
            for child in entry.rglob("*"):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    found.append(child)
        elif entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            found.append(entry)
    return found


def build_thumbnail_path(cache_dir: Path, source: Path, size: int) -> Path:
    safe_name = source.resolve().as_posix().lstrip("/").replace(":", "")
    safe_name = safe_name.replace("/", "__")
    filename = f"{safe_name}_{size}.jpg"
    return cache_dir / filename


def generate_thumbnail(
    source: Path,
    output_path: Path,
    size: int,
) -> ThumbnailResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image.save(output_path, format="JPEG", quality=90, optimize=True)
        width, height = image.size
    return ThumbnailResult(source, size, output_path, width, height)


def generate_thumbnails(
    sources: Iterable[Path],
    cache_dir: Path,
    sizes: Iterable[int],
) -> list[ThumbnailResult]:
    results: list[ThumbnailResult] = []
    normalized_sizes = [int(size) for size in sizes]
    for source in sources:
        for size in normalized_sizes:
            output_path = build_thumbnail_path(cache_dir, source, size)
            results.append(generate_thumbnail(source, output_path, size))
    return results


def to_thumbnail_record(result: ThumbnailResult) -> dict[str, str | int]:
    return {
        "photo_path": str(result.source.resolve()),
        "size": result.size,
        "path": str(result.output_path.resolve()),
        "width": result.width,
        "height": result.height,
    }
