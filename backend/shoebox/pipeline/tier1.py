"""Tier-1 photo ingestion pipeline.

Runs synchronously per uploaded file. Cheap operations only:
- SHA-256 of the bytes (exact-dup key);
- EXIF capture-time and GPS;
- perceptual hash (imagehash.phash, near-dup signal);
- thumbnails at small and medium widths.

Heavier work (CLIP embeddings, burst clustering, theme proposal) lives
in tier-2 and runs on demand. See ``shoebox.pipeline.tier2``.

The pipeline is decoupled from HTTP: it takes paths and returns plain
dataclasses. The upload handler is the only place that calls it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import imagehash
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()


class ImageDecodeError(ValueError):
    """The submitted file could not be decoded as an image."""

_EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}
_GPS_TAGS = {v: k for k, v in ExifTags.GPSTAGS.items()}


@dataclass(slots=True)
class IngestedPhoto:
    """Result of tier-1 ingestion for one file."""

    file_hash: str
    phash: str | None
    captured_at: str | None
    gps_lat: float | None
    gps_lon: float | None
    width: int
    height: int


def sha256_of(stream: BinaryIO) -> str:
    """Stream-hash a file-like object. Leaves cursor at end."""
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(chunk)
    return h.hexdigest()


def sha256_of_path(path: Path) -> str:
    with path.open("rb") as f:
        return sha256_of(f)


def _exif_datetime(image: Image.Image) -> str | None:
    raw = image.getexif() if hasattr(image, "getexif") else None
    if not raw:
        return None
    candidates = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")
    for tag_name in candidates:
        tag_id = _EXIF_TAGS.get(tag_name)
        if tag_id is None:
            continue
        value = raw.get(tag_id)
        if not value:
            continue
        try:
            # EXIF format: "YYYY:MM:DD HH:MM:SS".
            return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            continue
    return None


def _exif_gps(image: Image.Image) -> tuple[float | None, float | None]:
    raw = image.getexif() if hasattr(image, "getexif") else None
    if not raw:
        return None, None
    gps_ifd_tag = _EXIF_TAGS.get("GPSInfo")
    if gps_ifd_tag is None:
        return None, None
    gps = raw.get_ifd(gps_ifd_tag) if hasattr(raw, "get_ifd") else None
    if not gps:
        return None, None

    def _to_degrees(value: tuple) -> float:
        d, m, s = value
        return float(d) + float(m) / 60.0 + float(s) / 3600.0

    try:
        lat = _to_degrees(gps[_GPS_TAGS["GPSLatitude"]])
        if gps[_GPS_TAGS["GPSLatitudeRef"]] in ("S", b"S"):
            lat = -lat
        lon = _to_degrees(gps[_GPS_TAGS["GPSLongitude"]])
        if gps[_GPS_TAGS["GPSLongitudeRef"]] in ("W", b"W"):
            lon = -lon
        return lat, lon
    except (KeyError, TypeError, ValueError):
        return None, None


def ingest_file(
    *,
    source_path: Path,
    thumbs_dir: Path,
    medium_dir: Path,
    thumb_small_width: int,
    thumb_medium_width: int,
) -> IngestedPhoto:
    """Run tier-1 on a single image already on disk.

    Writes thumbnails next to ``thumbs_dir`` and ``medium_dir`` keyed by
    the file hash. Returns the values the DAO needs to persist.
    """
    file_hash = sha256_of_path(source_path)
    try:
        with Image.open(source_path) as opened:
            opened.load()
            img = ImageOps.exif_transpose(opened)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageDecodeError("Image could not be decoded") from exc

    width, height = img.size
    try:
        captured_at = _exif_datetime(img)
        gps_lat, gps_lon = _exif_gps(img)
    except Exception as exc:
        raise ImageDecodeError("Image metadata could not be decoded") from exc

    phash_value: str | None
    try:
        phash_value = str(imagehash.phash(img))
    except Exception:  # pragma: no cover — pHash never blocks ingest
        phash_value = None

    thumbs_dir.mkdir(parents=True, exist_ok=True)
    medium_dir.mkdir(parents=True, exist_ok=True)
    _write_derivative(img, thumbs_dir / f"{file_hash}.jpg", thumb_small_width)
    _write_derivative(img, medium_dir / f"{file_hash}.jpg", thumb_medium_width)

    return IngestedPhoto(
        file_hash=file_hash,
        phash=phash_value,
        captured_at=captured_at,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        width=width,
        height=height,
    )


def _write_derivative(image: Image.Image, target: Path, width: int) -> None:
    if image.width <= width:
        scaled = image.copy()
    else:
        ratio = width / image.width
        scaled = image.resize((width, int(image.height * ratio)), Image.LANCZOS)
    rgb = scaled.convert("RGB")
    rgb.save(target, format="JPEG", quality=85, optimize=True)
