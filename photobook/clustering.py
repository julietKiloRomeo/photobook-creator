from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import base64
import json
import os
from pathlib import Path
import re
import tomllib
from typing import Any
import hashlib

import httpx
import imagehash
from PIL import Image, ImageOps

from photobook.project_store import (
    list_references,
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


@dataclass
class Signature:
    reference_id: int
    label: str
    source: Path
    phash: imagehash.ImageHash
    captured_at: datetime


def _parse_date(reference: dict[str, Any]) -> datetime:
    metadata = reference.get("metadata") or {}
    for key in ["date", "captured_at"]:
        value = metadata.get(key) if isinstance(metadata, dict) else None
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue

    created_at = reference.get("created_at")
    if isinstance(created_at, str):
        try:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            pass

    return datetime.now(timezone.utc)


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
        image = _open_image(source)
        if image is None:
            continue

        output.append(
            Signature(
                reference_id=int(reference["id"]),
                label=str(reference.get("label") or f"Photo {reference['id']}"),
                source=source,
                phash=imagehash.phash(image, hash_size=16),
                captured_at=_parse_date(reference),
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


def _cluster_duplicates(signatures: list[Signature], threshold: int = 6) -> list[list[Signature]]:
    if not signatures:
        return []

    parent = {sig.reference_id: sig.reference_id for sig in signatures}

    for idx, left in enumerate(signatures):
        for right in signatures[idx + 1 :]:
            if (left.phash - right.phash) <= threshold:
                _union(parent, left.reference_id, right.reference_id)

    groups: dict[int, list[Signature]] = defaultdict(list)
    for sig in signatures:
        groups[_find(parent, sig.reference_id)].append(sig)

    return [sorted(group, key=lambda sig: sig.reference_id) for group in groups.values() if len(group) > 1]


def _tokenize(label: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", label.lower()) if len(token) > 2]


def _stack_id(reference_ids: list[int]) -> str:
    digest = hashlib.sha1(",".join(str(rid) for rid in sorted(reference_ids)).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"s-{digest[:12]}"


def _cluster_stacks(signatures: list[Signature], duplicate_groups: list[list[Signature]]) -> list[dict[str, Any]]:
    consumed = {sig.reference_id for group in duplicate_groups for sig in group}
    stacks: list[dict[str, Any]] = []

    for group in duplicate_groups:
        ids = [sig.reference_id for sig in group]
        tokens = Counter(token for sig in group for token in _tokenize(sig.label))
        label = f"{(tokens.most_common(1)[0][0].title() if tokens else 'Duplicate')} set"
        stacks.append(
            {
                "stack_id": _stack_id(ids),
                "label": label,
                "reference_ids": sorted(ids),
                "order_key": min(sig.captured_at for sig in group),
            }
        )

    by_day: dict[str, list[Signature]] = defaultdict(list)
    for sig in signatures:
        if sig.reference_id in consumed:
            continue
        by_day[sig.captured_at.date().isoformat()].append(sig)

    for day in sorted(by_day):
        members = sorted(by_day[day], key=lambda sig: sig.reference_id)
        ids = [sig.reference_id for sig in members]
        tokens = Counter(token for sig in members for token in _tokenize(sig.label))
        label = f"{(tokens.most_common(1)[0][0].title() if tokens else 'Day')} shots"
        stacks.append(
            {
                "stack_id": _stack_id(ids),
                "label": label,
                "reference_ids": ids,
                "order_key": members[0].captured_at,
            }
        )

    stacks.sort(key=lambda item: (item["order_key"], item["stack_id"]))
    for stack in stacks:
        stack.pop("order_key", None)
    return stacks


def _load_gateway() -> dict[str, str] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    if api_key and base_url:
        return {"api_key": api_key, "base_url": base_url.rstrip("/"), "model": model}

    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        return None
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    provider = ((config.get("model_providers") or {}).get("topsoe") or {})
    key = provider.get("api_key") or provider.get("key")
    url = provider.get("base_url") or provider.get("url")
    model = provider.get("model") or "gpt-4.1-mini"
    if isinstance(key, str) and isinstance(url, str):
        return {"api_key": key, "base_url": url.rstrip("/"), "model": str(model)}
    return None


def _contact_sheet(signatures: list[Signature]) -> str | None:
    thumbs: list[Image.Image] = []
    for sig in signatures[:12]:
        image = _open_image(sig.source)
        if image is None:
            continue
        thumbs.append(ImageOps.fit(image, (180, 140)))
    if not thumbs:
        return None

    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 180, rows * 140), color=(22, 22, 22))
    for idx, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((idx % cols) * 180, (idx // cols) * 140))

    buf = BytesIO()
    sheet.save(buf, format="JPEG", quality=82)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _openai_theme_map(signatures: list[Signature], stacks: list[dict[str, Any]]) -> dict[str, str]:
    gateway = _load_gateway()
    if gateway is None or not stacks:
        return {}

    by_id = {sig.reference_id: sig for sig in signatures}
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Cluster these stacks into concise travel themes. "
                "Return JSON only: {\"items\":[{\"stack_id\":\"...\",\"theme\":\"...\"}]}."
            ),
        }
    ]

    for stack in stacks:
        members = [by_id[rid] for rid in stack["reference_ids"] if rid in by_id]
        sheet = _contact_sheet(members)
        if sheet is None:
            continue
        content.append({"type": "text", "text": f"stack_id={stack['stack_id']}; local_label={stack['label']}"})
        content.append({"type": "image_url", "image_url": {"url": sheet}})

    payload = {
        "model": gateway["model"],
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                f"{gateway['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {gateway['api_key']}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        body = data["choices"][0]["message"]["content"]
        parsed = json.loads(body)
    except Exception:
        return {}

    result: dict[str, str] = {}
    for item in parsed.get("items", []):
        stack_id = item.get("stack_id")
        theme = item.get("theme")
        if isinstance(stack_id, str) and isinstance(theme, str) and theme.strip():
            result[stack_id] = theme.strip()
    return result


def _local_theme_clusters(signatures: list[Signature], stacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {sig.reference_id: sig for sig in signatures}
    groups: dict[str, list[str]] = defaultdict(list)
    for stack in stacks:
        ids = stack["reference_ids"]
        first = by_id.get(ids[0]) if ids else None
        key = first.captured_at.strftime("%B %Y") if first else "Ungrouped"
        groups[key].append(stack["stack_id"])

    clusters = [{"title": title, "stack_ids": sorted(stack_ids)} for title, stack_ids in groups.items()]
    clusters.sort(key=lambda item: item["title"])
    return clusters


def run_clustering_pipeline(db_path: Path) -> dict[str, Any]:
    references = list_references(db_path)
    signatures = _compute_signatures(references)

    if not signatures:
        set_duplicate_groups(db_path, [])
        set_stack_clusters(db_path, [])
        replace_themes_from_clusters(db_path, [])
        return {
            "references": len(references),
            "image_references": 0,
            "duplicate_groups": 0,
            "stacks": 0,
            "themes": 0,
            "openai_enriched": False,
        }

    duplicates = _cluster_duplicates(signatures)
    duplicate_payload: list[dict[str, Any]] = []
    for idx, group in enumerate(duplicates, start=1):
        anchor = group[0]
        duplicate_payload.append(
            {
                "group_id": f"dup-{idx}",
                "members": [
                    {"reference_id": sig.reference_id, "distance": int(anchor.phash - sig.phash)}
                    for sig in group
                ],
            }
        )
    set_duplicate_groups(db_path, duplicate_payload)

    stacks = _cluster_stacks(signatures, duplicates)
    set_stack_clusters(db_path, stacks)

    local_theme_clusters = _local_theme_clusters(signatures, stacks)
    theme_map = _openai_theme_map(signatures, stacks)

    if theme_map:
        grouped: dict[str, list[str]] = defaultdict(list)
        for stack in stacks:
            title = theme_map.get(stack["stack_id"], "Ungrouped")
            grouped[title].append(stack["stack_id"])
        theme_clusters = [
            {"title": title, "stack_ids": sorted(stack_ids)}
            for title, stack_ids in grouped.items()
        ]
        theme_clusters.sort(key=lambda item: item["title"])
    else:
        theme_clusters = local_theme_clusters

    themes = replace_themes_from_clusters(db_path, theme_clusters)

    return {
        "references": len(references),
        "image_references": len(signatures),
        "duplicate_groups": len(duplicate_payload),
        "stacks": len(stacks),
        "themes": len(themes),
        "openai_enriched": bool(theme_map),
    }
