from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps

from photobook.project_store import list_thumbnail_paths, upsert_photo_scores

MODEL_NAME = "ViT-L-14"
MODEL_PRETRAINED = "laion2b_s32b_b82k"
HEAD_FILENAME = "sa_0_4_vit_l_14_linear.pth"
HEAD_URL = (
    "https://github.com/LAION-AI/aesthetic-predictor/blob/main/"
    "sa_0_4_vit_l_14_linear.pth?raw=true"
)
MODEL_ID = "laion/CLIP-ViT-L-14-laion2B-s32B-b82K+sa_0_4_vit_l_14_linear"


@dataclass(frozen=True)
class ScoreResult:
    photo_path: str
    score: float
    model: str
    device: str


def _ensure_head_weights(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / HEAD_FILENAME
    if target.exists():
        return target
    with urllib.request.urlopen(HEAD_URL) as response:
        target.write_bytes(response.read())
    return target


def _normalize_head_state(state: dict[str, object]) -> dict[str, object]:
    if "state_dict" in state and isinstance(state["state_dict"], dict):
        state = state["state_dict"]
    if "bias" in state and "weight" in state:
        return {"weight": state["weight"], "bias": state.get("bias")}
    if "linear.weight" in state:
        return {
            "weight": state["linear.weight"],
            "bias": state.get("linear.bias"),
        }
    if "model.linear.weight" in state:
        return {
            "weight": state["model.linear.weight"],
            "bias": state.get("model.linear.bias"),
        }
    return {}


def _load_models(cache_dir: Path):
    import open_clip
    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _, preprocess = open_clip.create_model_and_transforms(
        MODEL_NAME, pretrained=MODEL_PRETRAINED
    )
    model = model.to(device)
    model.eval()
    head_path = _ensure_head_weights(cache_dir)
    state = torch.load(head_path, map_location=device)
    input_dim = getattr(model.visual, "output_dim", 768)
    head = torch.nn.Linear(int(input_dim), 1)
    head_state = _normalize_head_state(state if isinstance(state, dict) else {})
    if not head_state:
        raise ValueError("Unexpected aesthetic head checkpoint format")
    head.load_state_dict(head_state, strict=False)
    head = head.to(device)
    head.eval()
    return model, preprocess, head, device


def _iter_batches(
    items: list[tuple[str, str]], batch_size: int
) -> Iterable[list[tuple[str, str]]]:
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


def score_thumbnails(
    db_path: Path,
    cache_dir: Path,
    size: int = 256,
    batch_size: int = 24,
) -> int:
    thumbnail_paths = list_thumbnail_paths(db_path, size)
    items = sorted(thumbnail_paths.items())
    if not items:
        return 0

    model, preprocess, head, device = _load_models(cache_dir)
    import torch

    total = 0
    for batch in _iter_batches(items, batch_size):
        images = []
        photo_paths = []
        for photo_path, thumb_path in batch:
            with Image.open(thumb_path) as image:
                image = ImageOps.exif_transpose(image)
                image = image.convert("RGB")
                images.append(preprocess(image))
                photo_paths.append(photo_path)
        if not images:
            continue
        image_tensor = torch.stack(images).to(device)
        with torch.no_grad():
            features = model.encode_image(image_tensor)
            features = features / features.norm(dim=-1, keepdim=True)
            scores = head(features).squeeze(-1).float().cpu().tolist()
        timestamp = datetime.now(timezone.utc).isoformat()
        records = [
            {
                "photo_path": path,
                "score": float(score),
                "model": MODEL_ID,
                "device": str(device),
                "computed_at": timestamp,
            }
            for path, score in zip(photo_paths, scores, strict=False)
        ]
        upsert_photo_scores(db_path, records)
        total += len(records)
    return total
