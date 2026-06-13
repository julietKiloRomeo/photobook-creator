from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import base64
import hashlib
import os
from pathlib import Path
import re
import tempfile
import tomllib
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageOps
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from photobook.project_store import (
    assign_stack_theme,
    create_theme,
    list_themes,
    list_stacks,
    list_references,
    list_stack_split_overrides,
    replace_themes_from_clusters,
    set_duplicate_groups,
    set_stack_clusters,
)

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

DUPLICATE_DISTANCE_THRESHOLD = 8
STACK_SIMILARITY_THRESHOLD = 0.93
EXIF_PARTITION_HOURS = 6
CONTACT_SHEET_COLS = 4
CONTACT_SHEET_ROWS = 4
CONTACT_SHEET_TILE = (180, 140)


@dataclass
class Signature:
    reference_id: int
    label: str
    source: Path
    captured_at: datetime | None


class ThemeAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: int
    decision: str = Field(pattern="^(existing|new|unknown)$")
    theme_title: str | None = None


class ThemeBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignments: list[ThemeAssignment]


class ThemeReassignError(RuntimeError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_exif_datetime_value(value: Any) -> datetime | None:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    try:
        parsed = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _extract_exif_datetime(path: Path) -> datetime | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except Exception:
        return None

    if not exif:
        return None

    for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
        parsed = _parse_exif_datetime_value(exif.get(tag))
        if parsed is not None:
            return parsed
    return None


def _parse_date(reference: dict[str, Any], *, source: Path) -> datetime | None:
    # EXIF timestamp is preferred and file dates are intentionally ignored.
    exif_ts = _extract_exif_datetime(source)
    if exif_ts is not None:
        return exif_ts

    metadata = reference.get("metadata") or {}
    if isinstance(metadata, dict):
        for key in ["captured_at", "date"]:
            value = metadata.get(key)
            if isinstance(value, str):
                parsed = _parse_iso_datetime(value)
                if parsed is not None:
                    return parsed

    created_at = reference.get("created_at")
    if isinstance(created_at, str):
        parsed = _parse_iso_datetime(created_at)
        if parsed is not None:
            return parsed

    return None


def _open_image(path: Path) -> Image.Image | None:
    try:
        image = Image.open(path)
        return ImageOps.exif_transpose(image).convert("RGB")
    except Exception:
        return None


def _compute_signatures(references: list[dict[str, Any]]) -> list[Signature]:
    output: list[Signature] = []
    for reference in references:
        source = Path(str(reference["source"]))
        if source.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            continue
        if not source.exists() or not source.is_file():
            continue

        output.append(
            Signature(
                reference_id=int(reference["id"]),
                label=str(reference.get("label") or f"Photo {reference['id']}"),
                source=source,
                captured_at=_parse_date(reference, source=source),
            )
        )
    return output


def _find(parent: dict[int, int], item: int) -> int:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item


def _union(parent: dict[int, int], left: int, right: int) -> None:
    root_left = _find(parent, left)
    root_right = _find(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def _dedupe_fallback(signatures: list[Signature]) -> tuple[list[list[Signature]], bool]:
    try:
        import imagehash
    except Exception:
        return [], False

    hashed: list[tuple[Signature, imagehash.ImageHash]] = []
    for sig in signatures:
        image = _open_image(sig.source)
        if image is None:
            continue
        hashed.append((sig, imagehash.phash(image, hash_size=16)))

    if not hashed:
        return [], False

    parent = {sig.reference_id: sig.reference_id for sig, _ in hashed}
    for idx, (left_sig, left_hash) in enumerate(hashed):
        for right_sig, right_hash in hashed[idx + 1 :]:
            if int(left_hash - right_hash) <= 6:
                _union(parent, left_sig.reference_id, right_sig.reference_id)

    groups: dict[int, list[Signature]] = defaultdict(list)
    for sig, _ in hashed:
        groups[_find(parent, sig.reference_id)].append(sig)

    duplicates = [
        sorted(group, key=lambda item: item.reference_id)
        for group in groups.values()
        if len(group) > 1
    ]
    return duplicates, False


def _cluster_duplicates(signatures: list[Signature]) -> tuple[list[list[Signature]], bool]:
    if not signatures:
        return [], False

    try:
        from imagededup.methods import PHash
    except Exception:
        return _dedupe_fallback(signatures)

    index_by_file: dict[str, Signature] = {}
    with tempfile.TemporaryDirectory(prefix="photobook-dedupe-") as tmp:
        tmp_dir = Path(tmp)
        for sig in signatures:
            # Keep a stable lookup key that maps back to reference ids.
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", sig.source.name)
            file_name = f"r{sig.reference_id}_{safe_name}".strip("_")
            target = tmp_dir / file_name
            try:
                os.symlink(sig.source, target)
            except OSError:
                target.write_bytes(sig.source.read_bytes())
            index_by_file[file_name] = sig

        try:
            phasher = PHash()
            encodings = phasher.encode_images(image_dir=str(tmp_dir))
            duplicates_map = phasher.find_duplicates(
                encoding_map=encodings,
                max_distance_threshold=DUPLICATE_DISTANCE_THRESHOLD,
            )
        except Exception:
            return _dedupe_fallback(signatures)

    parent = {sig.reference_id: sig.reference_id for sig in signatures}
    for anchor_name, duplicate_names in duplicates_map.items():
        anchor = index_by_file.get(anchor_name)
        if anchor is None:
            continue
        for candidate_name in duplicate_names:
            candidate = index_by_file.get(candidate_name)
            if candidate is None:
                continue
            _union(parent, anchor.reference_id, candidate.reference_id)

    groups: dict[int, list[Signature]] = defaultdict(list)
    for sig in signatures:
        groups[_find(parent, sig.reference_id)].append(sig)

    duplicate_groups = [
        sorted(group, key=lambda item: item.reference_id)
        for group in groups.values()
        if len(group) > 1
    ]
    return duplicate_groups, True


def _tokenize(label: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", label.lower()) if len(token) > 2]


def _stack_id(reference_ids: list[int], *, salt: str = "") -> str:
    key = f"{','.join(str(rid) for rid in sorted(reference_ids))}|{salt}"
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"s-{digest[:12]}"


def _build_stack_label(signatures: list[Signature], fallback: str) -> str:
    tokens = Counter(token for sig in signatures for token in _tokenize(sig.label))
    return tokens.most_common(1)[0][0].title() if tokens else fallback


def _partition_signatures(signatures: list[Signature]) -> list[list[Signature]]:
    if not signatures:
        return []

    known = sorted(
        [sig for sig in signatures if sig.captured_at is not None],
        key=lambda item: (item.captured_at, item.reference_id),
    )
    unknown = sorted(
        [sig for sig in signatures if sig.captured_at is None],
        key=lambda item: item.reference_id,
    )

    partitions: list[list[Signature]] = []
    current: list[Signature] = []
    previous: datetime | None = None
    max_gap = timedelta(hours=EXIF_PARTITION_HOURS)

    for sig in known:
        if not current:
            current = [sig]
            previous = sig.captured_at
            continue

        if previous is None or sig.captured_at is None:
            current.append(sig)
            previous = sig.captured_at
            continue

        if (sig.captured_at - previous) <= max_gap:
            current.append(sig)
        else:
            partitions.append(current)
            current = [sig]
        previous = sig.captured_at

    if current:
        partitions.append(current)

    if unknown:
        partitions.append(unknown)

    return partitions


def _compute_clip_embeddings(signatures: list[Signature]) -> tuple[dict[int, list[float]], bool]:
    if not signatures:
        return {}, False

    try:
        import torch
        import open_clip
    except Exception:
        return {}, False

    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="laion2b_s34b_b79k",
            device=device,
        )
        model.eval()
    except Exception:
        return {}, False

    embeddings: dict[int, list[float]] = {}
    with torch.no_grad():
        batch_size = 16
        for start in range(0, len(signatures), batch_size):
            chunk = signatures[start : start + batch_size]
            tensors = []
            refs: list[int] = []
            for sig in chunk:
                image = _open_image(sig.source)
                if image is None:
                    continue
                tensors.append(preprocess(image))
                refs.append(sig.reference_id)

            if not tensors:
                continue

            batch = torch.stack(tensors).to(device)
            features = model.encode_image(batch)
            features = features / features.norm(dim=-1, keepdim=True)
            vectors = features.detach().cpu().tolist()
            for ref_id, vec in zip(refs, vectors):
                embeddings[ref_id] = [float(value) for value in vec]

    return embeddings, True


def _dot(left: list[float], right: list[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right)))


def _cluster_partition_by_similarity(signatures: list[Signature], embeddings: dict[int, list[float]]) -> list[list[Signature]]:
    if not signatures:
        return []

    clustered = [sig for sig in signatures if sig.reference_id in embeddings]
    unembedded = [sig for sig in signatures if sig.reference_id not in embeddings]

    groups: list[list[Signature]] = []
    if clustered:
        parent = {sig.reference_id: sig.reference_id for sig in clustered}
        for idx, left in enumerate(clustered):
            left_vec = embeddings[left.reference_id]
            for right in clustered[idx + 1 :]:
                sim = _dot(left_vec, embeddings[right.reference_id])
                if sim >= STACK_SIMILARITY_THRESHOLD:
                    _union(parent, left.reference_id, right.reference_id)

        grouped: dict[int, list[Signature]] = defaultdict(list)
        for sig in clustered:
            grouped[_find(parent, sig.reference_id)].append(sig)
        groups.extend(grouped.values())

    for sig in unembedded:
        groups.append([sig])

    return [sorted(group, key=lambda item: item.reference_id) for group in groups]


def _cluster_stacks(
    signatures: list[Signature],
    duplicate_groups: list[list[Signature]],
    *,
    use_clip: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    consumed = {sig.reference_id for group in duplicate_groups for sig in group}
    stacks: list[dict[str, Any]] = []

    # Keep near duplicates together in dedicated stacks.
    for group in duplicate_groups:
        ids = [sig.reference_id for sig in group]
        order_key = min((sig.captured_at or datetime.now(timezone.utc)) for sig in group)
        stacks.append(
            {
                "stack_id": _stack_id(ids),
                "label": _build_stack_label(group, "Duplicate"),
                "reference_ids": sorted(ids),
                "order_key": order_key,
            }
        )

    candidates = [sig for sig in signatures if sig.reference_id not in consumed]
    if not candidates:
        stacks.sort(key=lambda item: (item["order_key"], item["stack_id"]))
        for stack in stacks:
            stack.pop("order_key", None)
        return stacks, False

    embeddings, clip_available = ({}, False)
    if use_clip:
        embeddings, clip_available = _compute_clip_embeddings(candidates)
    partitions = _partition_signatures(candidates)

    for part_index, partition in enumerate(partitions):
        if clip_available:
            grouped = _cluster_partition_by_similarity(partition, embeddings)
        else:
            # Conservative fallback: no CLIP runtime means avoid false merges.
            grouped = [[sig] for sig in partition]

        for cluster_index, group in enumerate(grouped):
            ids = [sig.reference_id for sig in group]
            order_key = min((sig.captured_at or datetime.now(timezone.utc)) for sig in group)
            fallback = "Unknown" if all(sig.captured_at is None for sig in group) else "Moments"
            label = _build_stack_label(group, fallback)
            stacks.append(
                {
                    "stack_id": _stack_id(ids, salt=f"p{part_index}-c{cluster_index}"),
                    "label": label,
                    "reference_ids": sorted(ids),
                    "order_key": order_key,
                }
            )

    stacks.sort(key=lambda item: (item["order_key"], item["stack_id"]))
    for stack in stacks:
        stack.pop("order_key", None)
    return stacks, clip_available


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    output: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            output[key] = value
    return output


def _resolve_env_value(key: str, dotenv: dict[str, str]) -> str | None:
    current = os.getenv(key)
    if isinstance(current, str) and current.strip():
        return current.strip()
    value = dotenv.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _load_gateway() -> dict[str, str] | None:
    dotenv = {}
    for path in (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ):
        dotenv.update(_load_dotenv(path))

    api_key = _resolve_env_value("OPENAI_API_KEY", dotenv)
    base_url = _resolve_env_value("OPENAI_BASE_URL", dotenv)
    model = _resolve_env_value("OPENAI_MODEL", dotenv) or "gpt-4.1-mini"
    if api_key and base_url:
        return {"api_key": api_key, "base_url": base_url.rstrip("/"), "model": model}

    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        return None
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    providers = config.get("model_providers") or {}
    provider_name = config.get("model_provider")
    provider = {}
    if isinstance(provider_name, str):
        provider = providers.get(provider_name) or {}
    if not provider:
        provider = providers.get("topsoe") or {}

    env_key = provider.get("env_key")
    key = None
    if isinstance(env_key, str) and env_key.strip():
        key = _resolve_env_value(env_key.strip(), dotenv)
    if key is None:
        key = provider.get("api_key") or provider.get("key")

    url = provider.get("base_url") or provider.get("url")
    model = (
        _resolve_env_value("OPENAI_MODEL", dotenv)
        or provider.get("model")
        or config.get("model")
        or "gpt-4.1-mini"
    )
    if isinstance(key, str) and isinstance(url, str):
        return {"api_key": key, "base_url": url.rstrip("/"), "model": str(model)}
    return None


def _contact_sheet(signatures: list[Signature]) -> tuple[str | None, list[dict[str, Any]]]:
    if not signatures:
        return None, []

    max_items = CONTACT_SHEET_COLS * CONTACT_SHEET_ROWS
    selected = signatures[:max_items]
    sheet = Image.new(
        "RGB",
        (CONTACT_SHEET_COLS * CONTACT_SHEET_TILE[0], CONTACT_SHEET_ROWS * CONTACT_SHEET_TILE[1]),
        color=(18, 18, 18),
    )
    draw = ImageDraw.Draw(sheet)

    mapping: list[dict[str, Any]] = []
    for idx, sig in enumerate(selected):
        image = _open_image(sig.source)
        if image is None:
            continue
        thumb = ImageOps.fit(image, CONTACT_SHEET_TILE)
        x = (idx % CONTACT_SHEET_COLS) * CONTACT_SHEET_TILE[0]
        y = (idx // CONTACT_SHEET_COLS) * CONTACT_SHEET_TILE[1]
        sheet.paste(thumb, (x, y))

        marker = f"#{sig.reference_id}"
        draw.rectangle((x + 6, y + 6, x + 82, y + 28), fill=(0, 0, 0, 165))
        draw.text((x + 10, y + 10), marker, fill=(255, 255, 255))

        mapping.append({
            "reference_id": sig.reference_id,
            "label": sig.label,
            "marker": marker,
        })

    if not mapping:
        return None, []

    buf = BytesIO()
    sheet.save(buf, format="JPEG", quality=84)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", mapping


def _normalize_theme_title(value: str) -> str:
    normalized = " ".join(value.strip().split())
    return normalized[:80] if normalized else ""


def _theme_assignment_schema() -> dict[str, Any]:
    # Azure/OpenAI Responses strict schemas require every property key in `required`,
    # including nullable fields such as `theme_title`.
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "reference_id": {"type": "integer"},
                        "decision": {"type": "string", "enum": ["existing", "new", "unknown"]},
                        "theme_title": {"type": ["string", "null"]},
                    },
                    "required": ["reference_id", "decision", "theme_title"],
                },
            }
        },
        "required": ["assignments"],
    }


def _openai_theme_map(
    signatures: list[Signature],
    stacks: list[dict[str, Any]],
    *,
    existing_themes: list[dict[str, Any]] | None = None,
) -> tuple[dict[int, str], bool, dict[str, Any]]:
    gateway = _load_gateway()
    if gateway is None:
        return {}, False, {"reason": "no_gateway_config", "successful_batches": 0, "error_batches": 0}
    if not signatures:
        return {}, False, {"reason": "no_signatures", "successful_batches": 0, "error_batches": 0}

    schema = _theme_assignment_schema()
    assignments: dict[int, str] = {}
    known_theme_map: dict[str, str] = {}
    known_theme_details: list[tuple[str, str]] = []
    for theme in existing_themes or []:
        title = _normalize_theme_title(str(theme.get("title") or ""))
        if not title:
            continue
        detail = " ".join(str(theme.get("description") or "").split())[:220]
        key = title.lower()
        if key in known_theme_map:
            continue
        known_theme_map[key] = title
        known_theme_details.append((title, detail))

    ordered = sorted(
        signatures,
        key=lambda sig: (
            sig.captured_at or datetime(1970, 1, 1, tzinfo=timezone.utc),
            sig.reference_id,
        ),
    )

    batch_size = CONTACT_SHEET_COLS * CONTACT_SHEET_ROWS
    successful_batches = 0
    error_batches = 0
    last_error_reason: str | None = None
    for start in range(0, len(ordered), batch_size):
        batch = ordered[start : start + batch_size]
        sheet, mapping = _contact_sheet(batch)
        if sheet is None or not mapping:
            continue

        mapping_text = "\n".join(
            f"{item['marker']} reference_id={item['reference_id']} label={item['label']}"
            for item in mapping
        )
        if known_theme_details:
            known_text = "\n".join(
                f"- {title}: {detail or '(no description)'}"
                for title, detail in known_theme_details
            )
        else:
            known_text = "(none yet)"

        prompt = (
            "Assign each photo to an existing theme, a new theme, or unknown. "
            "Prefer existing themes when they fit.\n"
            "Decisions: existing | new | unknown.\n"
            "If decision is unknown, theme_title must be null.\n"
            "If decision is existing/new, theme_title must be a short title.\n"
            "If decision is existing, theme_title must exactly match one known theme title.\n"
            "Known themes (title: description):\n"
            f"{known_text}\n"
            "Photo mapping:\n"
            f"{mapping_text}"
        )

        payload = {
            "model": gateway["model"],
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": sheet},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "theme_batch_assignments",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

        try:
            base_url = str(gateway["base_url"]).rstrip("/")
            headers = {"Content-Type": "application/json"}
            if ".azure.com" in base_url:
                headers["api-key"] = str(gateway["api_key"])
            else:
                headers["Authorization"] = f"Bearer {gateway['api_key']}"
            with httpx.Client(timeout=90.0) as client:
                response = client.post(
                    f"{base_url}/v1/responses",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            output_text = data.get("output_text")
            if not output_text:
                for item in data.get("output", []):
                    if not isinstance(item, dict) or item.get("type") != "message":
                        continue
                    for part in item.get("content", []):
                        if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                            output_text = (output_text or "") + str(part.get("text") or "")
            if not isinstance(output_text, str) or not output_text.strip():
                error_batches += 1
                last_error_reason = "invalid_response_payload"
                continue

            parsed = ThemeBatchResult.model_validate_json(output_text)
            successful_batches += 1
        except httpx.HTTPError:
            error_batches += 1
            last_error_reason = "llm_http_error"
            continue
        except (ValidationError, ValueError, KeyError, TypeError):
            error_batches += 1
            last_error_reason = "schema_parse_failed"
            continue

        seen = {item["reference_id"] for item in mapping}
        for item in parsed.assignments:
            if item.reference_id not in seen:
                continue

            decision = item.decision
            title = _normalize_theme_title(item.theme_title or "")
            if decision == "unknown":
                assignments[item.reference_id] = "unknown"
                continue

            if not title:
                assignments[item.reference_id] = "unknown"
                continue

            if decision == "existing":
                known = known_theme_map.get(title.lower())
                if known:
                    assignments[item.reference_id] = known
                else:
                    assignments[item.reference_id] = "unknown"
                continue

            # decision == new
            assignments[item.reference_id] = title
            key = title.lower()
            if key not in known_theme_map:
                known_theme_map[key] = title
                known_theme_details.append((title, ""))

        # Keep discovered themes from this batch available for the next batch.
        for assigned in assignments.values():
            if assigned == "unknown":
                continue
            key = assigned.lower()
            if key not in known_theme_map:
                known_theme_map[key] = assigned
                known_theme_details.append((assigned, ""))

    if assignments:
        return assignments, True, {
            "reason": "ok",
            "successful_batches": successful_batches,
            "error_batches": error_batches,
        }

    if successful_batches > 0:
        return {}, True, {
            "reason": "no_confident_matches",
            "successful_batches": successful_batches,
            "error_batches": error_batches,
        }

    return {}, True, {
        "reason": last_error_reason or "no_llm_output",
        "successful_batches": successful_batches,
        "error_batches": error_batches,
    }


def _local_theme_clusters(signatures: list[Signature], stacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {sig.reference_id: sig for sig in signatures}
    groups: dict[str, list[str]] = defaultdict(list)
    for stack in stacks:
        ids = stack["reference_ids"]
        first = by_id.get(ids[0]) if ids else None
        if first is None or first.captured_at is None:
            key = "Ungrouped"
        else:
            key = first.captured_at.strftime("%B %Y")
        groups[key].append(stack["stack_id"])

    clusters = [{"title": title, "stack_ids": sorted(stack_ids)} for title, stack_ids in groups.items()]
    clusters.sort(key=lambda item: item["title"])
    return clusters


def _themes_from_photo_assignments(stacks: list[dict[str, Any]], assignments: dict[int, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for stack in stacks:
        counts: Counter[str] = Counter()
        for ref_id in stack["reference_ids"]:
            assigned = assignments.get(int(ref_id))
            if not assigned or assigned == "unknown":
                continue
            counts[assigned] += 1

        theme = counts.most_common(1)[0][0] if counts else "Ungrouped"
        grouped[theme].append(str(stack["stack_id"]))

    clusters = [{"title": title, "stack_ids": sorted(stack_ids)} for title, stack_ids in grouped.items()]
    clusters.sort(key=lambda item: item["title"])
    return clusters


def rerun_theme_assignment_pipeline(db_path: Path) -> dict[str, Any]:
    existing_themes = list_themes(db_path)
    stacks_rows = list_stacks(db_path)
    if not stacks_rows:
        return {
            "stacks_total": 0,
            "unassigned_stacks": 0,
            "assigned_stacks": 0,
            "created_themes": 0,
            "structured_outputs_used": False,
            "openai_enriched": False,
            "reason": "no_stacks",
        }
    assigned_stack_ids = {str(sid) for theme in existing_themes for sid in theme.get("stack_ids", [])}
    unassigned_stack_ids = {str(item["id"]) for item in stacks_rows if str(item["id"]) not in assigned_stack_ids}
    if not unassigned_stack_ids:
        return {
            "stacks_total": len(stacks_rows),
            "unassigned_stacks": 0,
            "assigned_stacks": 0,
            "created_themes": 0,
            "structured_outputs_used": False,
            "openai_enriched": False,
            "reason": "no_unassigned_stacks",
        }

    stacks = [
        {
            "stack_id": str(item["id"]),
            "reference_ids": [int(ref_id) for ref_id in item.get("photo_ids", [])],
        }
        for item in stacks_rows
    ]
    signatures = _compute_signatures(list_references(db_path))
    theme_assignments, structured_outputs_used, map_meta = _openai_theme_map(
        signatures,
        stacks,
        existing_themes=existing_themes,
    )
    map_reason = str(map_meta.get("reason") or "unknown")
    if not theme_assignments:
        if map_reason != "no_confident_matches":
            raise ThemeReassignError(map_reason, f"AI theme assignment unavailable: {map_reason}")
        return {
            "stacks_total": len(stacks_rows),
            "unassigned_stacks": len(unassigned_stack_ids),
            "assigned_stacks": 0,
            "created_themes": 0,
            "structured_outputs_used": structured_outputs_used,
            "openai_enriched": False,
            "reason": map_reason,
        }

    predicted = _themes_from_photo_assignments(stacks, theme_assignments)

    theme_id_by_title = {
        _normalize_theme_title(str(theme.get("title") or "")).lower(): int(theme["id"])
        for theme in existing_themes
        if _normalize_theme_title(str(theme.get("title") or ""))
    }
    created_themes = 0
    assigned_stacks = 0

    for cluster in predicted:
        title = _normalize_theme_title(str(cluster.get("title") or ""))
        if not title:
            continue
        key = title.lower()
        theme_id = theme_id_by_title.get(key)
        if theme_id is None:
            created = create_theme(db_path, title)
            theme_id = int(created["id"])
            theme_id_by_title[key] = theme_id
            created_themes += 1
        for stack_id in cluster.get("stack_ids", []):
            sid = str(stack_id)
            if sid not in unassigned_stack_ids:
                continue
            assign_stack_theme(db_path, sid, theme_id)
            unassigned_stack_ids.discard(sid)
            assigned_stacks += 1

    return {
        "stacks_total": len(stacks_rows),
        "unassigned_stacks": len(unassigned_stack_ids),
        "assigned_stacks": assigned_stacks,
        "created_themes": created_themes,
        "structured_outputs_used": structured_outputs_used,
        "openai_enriched": bool(theme_assignments),
        "reason": "ok",
    }


def _apply_split_overrides(stacks: list[dict[str, Any]], overrides: dict[int, dict[str, str]]) -> list[dict[str, Any]]:
    if not overrides or not stacks:
        return stacks

    by_stack: dict[str, dict[str, Any]] = {}
    for index, stack in enumerate(stacks, start=1):
        by_stack[str(stack["stack_id"])] = {
            "stack_id": str(stack["stack_id"]),
            "label": str(stack.get("label") or f"Stack {index}"),
            "reference_ids": [int(item) for item in stack.get("reference_ids", [])],
            "order_index": index,
        }

    for reference_id, override in overrides.items():
        forced_stack = str(override.get("stack_id") or "").strip()
        if not forced_stack:
            continue

        for stack in by_stack.values():
            if reference_id in stack["reference_ids"]:
                stack["reference_ids"] = [rid for rid in stack["reference_ids"] if rid != reference_id]

        target = by_stack.get(forced_stack)
        if target is None:
            by_stack[forced_stack] = {
                "stack_id": forced_stack,
                "label": str(override.get("label") or "Custom split"),
                "reference_ids": [reference_id],
                "order_index": len(by_stack) + 1,
            }
            continue

        if reference_id not in target["reference_ids"]:
            target["reference_ids"].append(reference_id)
        if override.get("label"):
            target["label"] = str(override["label"])

    result = []
    for stack in sorted(by_stack.values(), key=lambda item: (item["order_index"], item["stack_id"])):
        unique_ids = sorted({int(rid) for rid in stack["reference_ids"]})
        if not unique_ids:
            continue
        result.append(
            {
                "stack_id": stack["stack_id"],
                "label": stack["label"],
                "reference_ids": unique_ids,
            }
        )

    return result


def run_clustering_pipeline(
    db_path: Path,
    *,
    mode: str = "final",
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    phase_mode = "final" if mode not in {"final", "provisional"} else mode
    is_provisional = phase_mode == "provisional"

    def _progress(step: str, percent: int, message: str) -> None:
        if callable(progress_callback):
            progress_callback(step, int(percent), message)

    _progress("scan", 5 if is_provisional else 2, "Loading references")
    references = list_references(db_path)
    signatures = _compute_signatures(references)

    if not signatures:
        _progress("duplicates", 30 if is_provisional else 18, "Clearing duplicate state")
        set_duplicate_groups(db_path, [])
        _progress("stacks", 65 if is_provisional else 45, "Clearing stack state")
        set_stack_clusters(db_path, [])
        if not is_provisional:
            replace_themes_from_clusters(db_path, [])
        themes = list_themes(db_path)
        _progress("finalize", 100, "No images to cluster")
        return {
            "references": len(references),
            "image_references": 0,
            "duplicate_groups": 0,
            "stacks": 0,
            "themes": len(themes),
            "openai_enriched": False,
            "structured_outputs_used": False,
            "clip_available": False,
            "imagededup_used": False,
            "exif_partition_hours": EXIF_PARTITION_HOURS,
            "mode": phase_mode,
        }

    _progress("duplicates", 35 if is_provisional else 18, "Detecting near duplicates")
    duplicate_groups, imagededup_used = _cluster_duplicates(signatures)
    duplicate_payload: list[dict[str, Any]] = []
    for idx, group in enumerate(duplicate_groups, start=1):
        duplicate_payload.append(
            {
                "group_id": f"dup-{idx}",
                "members": [
                    {
                        "reference_id": sig.reference_id,
                        "distance": 0,
                    }
                    for sig in group
                ],
            }
        )
    set_duplicate_groups(db_path, duplicate_payload)

    _progress("stacks", 70 if is_provisional else 45, "Building stack clusters")
    stacks, clip_available = _cluster_stacks(signatures, duplicate_groups, use_clip=not is_provisional)
    overrides = list_stack_split_overrides(db_path)
    stacks = _apply_split_overrides(stacks, overrides)
    set_stack_clusters(db_path, stacks)

    local_theme_clusters = _local_theme_clusters(signatures, stacks)
    theme_assignments: dict[int, str] = {}
    structured_outputs_used = False
    if not is_provisional:
        _progress("themes", 80, "Assigning theme clusters")
        theme_assignments, structured_outputs_used, _map_meta = _openai_theme_map(
            signatures,
            stacks,
            existing_themes=list_themes(db_path),
        )

    if theme_assignments:
        theme_clusters = _themes_from_photo_assignments(stacks, theme_assignments)
    else:
        theme_clusters = local_theme_clusters

    if is_provisional:
        themes = list_themes(db_path)
    else:
        themes = replace_themes_from_clusters(db_path, theme_clusters)

    _progress("finalize", 100, "Clustering complete")

    return {
        "references": len(references),
        "image_references": len(signatures),
        "duplicate_groups": len(duplicate_payload),
        "stacks": len(stacks),
        "themes": len(themes),
        "openai_enriched": bool(theme_assignments),
        "structured_outputs_used": structured_outputs_used,
        "clip_available": clip_available,
        "imagededup_used": imagededup_used,
        "exif_partition_hours": EXIF_PARTITION_HOURS,
        "mode": phase_mode,
    }
