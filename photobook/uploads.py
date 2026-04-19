from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from io import BytesIO
from pathlib import Path
import re
import uuid

from fastapi import UploadFile
from PIL import Image, ImageOps

try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    HEIF_ENABLED = True
except Exception:
    HEIF_ENABLED = False

from photobook.project_store import create_upload, upsert_references


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
    ".bmp",
    ".tif",
    ".tiff",
}


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return cleaned or "file"


def _normalize_relative_path(path: str | None) -> str | None:
    if not path:
        return None
    raw = path.replace("\\", "/").strip().lstrip("/")
    if not raw:
        return None

    parts: list[str] = []
    for part in raw.split("/"):
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        parts.append(_safe_name(part))

    if not parts:
        return None
    return "/".join(parts)


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _guess_image_supported(filename: str, content_type: str | None) -> bool:
    ext = Path(filename).suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return True
    if content_type and content_type.startswith("image/"):
        return True
    return False


def _open_image(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(BytesIO(data))
        return ImageOps.exif_transpose(image).convert("RGB")
    except Exception:
        return None


def _convert_to_jpeg(data: bytes) -> bytes | None:
    image = _open_image(data)
    if image is None:
        return None
    out = BytesIO()
    image.save(out, format="JPEG", quality=88)
    return out.getvalue()


@dataclass
class UploadResult:
    stored: int
    supported_images: int
    ignored: int
    created_references: int


def process_uploads(
    db_path: Path,
    originals_dir: Path,
    derived_dir: Path,
    files: list[UploadFile],
    relative_paths: list[str] | None = None,
) -> UploadResult:
    originals_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)

    created_references = 0
    supported_images = 0
    ignored = 0
    stored = 0

    normalized_relative_paths = relative_paths or []

    for index, incoming in enumerate(files):
        original_name = incoming.filename or "file"
        raw_relative_path = normalized_relative_paths[index] if index < len(normalized_relative_paths) else None
        relative_path = _normalize_relative_path(raw_relative_path)

        relative_filename = Path(relative_path).name if relative_path else original_name
        safe_name = _safe_name(relative_filename)
        ext = Path(safe_name).suffix.lower()
        prefix = uuid.uuid4().hex[:10]
        stored_name = f"{prefix}_{safe_name}"
        relative_parent = Path(relative_path).parent if relative_path else Path()
        original_path = originals_dir / relative_parent / stored_name
        original_path.parent.mkdir(parents=True, exist_ok=True)

        data = incoming.file.read()
        stored += 1
        sha = _sha256_bytes(data)

        original_path.write_bytes(data)
        size_bytes = len(data)
        content_type = incoming.content_type

        is_supported = _guess_image_supported(safe_name, content_type)
        ignored_reason: str | None = None
        derived_path: Path | None = None

        if is_supported:
            # HEIC support depends on pillow_heif registration.
            if ext in {".heic", ".heif"} and not HEIF_ENABLED:
                is_supported = False
                ignored_reason = "heic_not_supported"
            else:
                jpeg_data = _convert_to_jpeg(data)
                if jpeg_data is None:
                    is_supported = False
                    ignored_reason = "unsupported_image_data"
                else:
                    derived_name = f"{Path(stored_name).stem}.jpg"
                    derived_path = derived_dir / relative_parent / derived_name
                    derived_path.parent.mkdir(parents=True, exist_ok=True)
                    derived_path.write_bytes(jpeg_data)

        upload_id = create_upload(
            db_path,
            filename=original_name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha,
            original_path=str(original_path.resolve()),
            derived_path=str(derived_path.resolve()) if derived_path else None,
            is_supported_image=is_supported,
            ignored_reason=ignored_reason,
            metadata={
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "extension": ext,
                "heif_enabled": HEIF_ENABLED,
                "relative_path": relative_path,
                "stored_original_relative_path": str(original_path.relative_to(originals_dir)).replace("\\", "/"),
                "stored_derived_relative_path": (
                    str(derived_path.relative_to(derived_dir)).replace("\\", "/")
                    if derived_path is not None
                    else None
                ),
            },
        )

        if is_supported and derived_path is not None:
            supported_images += 1
            upsert_references(
                db_path,
                [
                    {
                        "source": str(derived_path.resolve()),
                        "source_type": "path",
                        "label": Path(original_name).stem,
                        "metadata": {
                            "upload_id": upload_id,
                            "original_filename": original_name,
                            "date": datetime.now(timezone.utc).date().isoformat(),
                        },
                    }
                ],
            )
            created_references += 1
        else:
            ignored += 1

    return UploadResult(
        stored=stored,
        supported_images=supported_images,
        ignored=ignored,
        created_references=created_references,
    )
