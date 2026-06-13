#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "openai>=1.100.0",
# ]
# ///

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib
from typing import Any
import urllib.request

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "tests" / "fixtures" / "vacation-20"
MANIFEST_PATH = OUT_DIR / "manifest.json"
DEFAULT_CODEX_CONFIG = Path.home() / ".codex" / "config.toml"


PROMPTS: list[dict[str, Any]] = [
    {"id": "vac-01", "tags": ["beach", "sunset", "boardwalk"], "prompt": "Photorealistic vacation photo, golden hour on a beach boardwalk with palm trees and gentle surf in the distance, candid travel snapshot, natural colors, no text, no watermark."},
    {"id": "vac-02", "tags": ["mountain", "lake", "hike"], "prompt": "Photorealistic vacation photo, alpine hiking trail above a turquoise mountain lake, bright clear sky, candid travel snapshot, no people close-up, no text, no watermark."},
    {"id": "vac-03", "tags": ["city", "old-town", "cafe"], "prompt": "Photorealistic vacation photo, historic European old-town square with outdoor cafe tables and warm evening light, candid travel style, no text, no watermark."},
    {"id": "vac-04", "tags": ["desert", "roadtrip", "cliffs"], "prompt": "Photorealistic vacation photo, desert roadside lookout with sandstone cliffs and a winding road, late afternoon light, candid travel style, no text, no watermark."},
    {"id": "vac-05", "tags": ["harbor", "boats", "island"], "prompt": "Photorealistic vacation photo, island harbor with small fishing boats in crystal blue water, bright daylight, candid travel snapshot, no text, no watermark."},
    {"id": "vac-06", "tags": ["market", "street", "food"], "prompt": "Photorealistic vacation photo, lively outdoor street market with colorful produce stalls and soft morning light, candid travel style, no text, no watermark."},
    {"id": "vac-07", "tags": ["forest", "waterfall", "trail"], "prompt": "Photorealistic vacation photo, forest trail leading to a cascading waterfall, misty atmosphere, handheld travel photography look, no text, no watermark."},
    {"id": "vac-08", "tags": ["coast", "cliffs", "panorama"], "prompt": "Photorealistic vacation photo, dramatic coastal cliffs with ocean panorama and whitecaps, overcast but bright sky, travel snapshot, no text, no watermark."},
    {"id": "vac-09", "tags": ["resort", "pool", "tropical"], "prompt": "Photorealistic vacation photo, tropical resort pool with lush greenery and sun umbrellas, midday sun, candid vacation style, no text, no watermark."},
    {"id": "vac-10", "tags": ["train", "window", "landscape"], "prompt": "Photorealistic vacation photo, scenic train ride view through a large window with rolling green hills, natural reflections, travel documentary feel, no text, no watermark."},
    {"id": "vac-11", "tags": ["beach", "sunrise", "shore"], "prompt": "Photorealistic vacation photo, early sunrise at a quiet sandy beach with footprints near shoreline, pastel sky, candid travel shot, no text, no watermark."},
    {"id": "vac-12", "tags": ["mountain", "village", "valley"], "prompt": "Photorealistic vacation photo, mountain valley with a small hillside village and winding road, soft golden light, candid travel style, no text, no watermark."},
    {"id": "vac-13", "tags": ["museum", "architecture", "city"], "prompt": "Photorealistic vacation photo, modern museum exterior with striking architecture in a clean city plaza, blue hour lighting, travel snapshot, no text, no watermark."},
    {"id": "vac-14", "tags": ["desert", "dunes", "sunset"], "prompt": "Photorealistic vacation photo, sweeping desert dunes at sunset with long shadows and warm tones, candid travel framing, no text, no watermark."},
    {"id": "vac-15", "tags": ["harbor", "night", "lights"], "prompt": "Photorealistic vacation photo, harbor promenade at night with reflected city lights on calm water, travel snapshot, no text, no watermark."},
    {"id": "vac-16", "tags": ["beach", "kayak", "lagoon"], "prompt": "Photorealistic vacation photo, colorful kayaks by a shallow turquoise lagoon, bright daylight and soft clouds, candid travel style, no text, no watermark."},
    {"id": "vac-17", "tags": ["mountain", "cabin", "pine"], "prompt": "Photorealistic vacation photo, rustic mountain cabin among pine trees with distant snowy peaks, crisp morning light, travel photo look, no text, no watermark."},
    {"id": "vac-18", "tags": ["city", "river", "bridge"], "prompt": "Photorealistic vacation photo, riverside city walk with stone bridge and bicycles, late afternoon light, candid travel snapshot, no text, no watermark."},
    {"id": "vac-19", "tags": ["desert", "canyon", "viewpoint"], "prompt": "Photorealistic vacation photo, canyon viewpoint with layered red rock formations and expansive sky, travel documentary style, no text, no watermark."},
    {"id": "vac-20", "tags": ["island", "pier", "boats"], "prompt": "Photorealistic vacation photo, wooden pier extending into clear island water with anchored boats, golden hour glow, candid travel style, no text, no watermark."},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 20 vacation fixture photos via OpenAI image generation through llm-gateway")
    parser.add_argument("--config", type=Path, default=DEFAULT_CODEX_CONFIG, help="Path to Codex config TOML")
    parser.add_argument("--provider", default="topsoe", help="Provider key in [model_providers]")
    parser.add_argument("--model", default="gpt-image-1", help="Image model id")
    parser.add_argument("--size", default="1024x1024", help="Image size")
    parser.add_argument("--quality", default="low", help="Image quality")
    return parser.parse_args()


def load_gateway_settings(config_path: Path, provider_name: str) -> tuple[str, str]:
    if not config_path.exists():
        raise RuntimeError(f"Codex config not found: {config_path}")

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    providers = config.get("model_providers")
    if not isinstance(providers, dict):
        raise RuntimeError("No [model_providers] table found in Codex config")

    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise RuntimeError(f"Provider '{provider_name}' not found under [model_providers]")

    base_url = str(provider.get("base_url", "")).strip()
    if not base_url:
        raise RuntimeError(f"Provider '{provider_name}' missing base_url")

    headers = provider.get("http_headers")
    if not isinstance(headers, dict):
        raise RuntimeError(f"Provider '{provider_name}' missing http_headers")

    auth = str(headers.get("Authorization", "")).strip()
    if not auth:
        raise RuntimeError(f"Provider '{provider_name}' missing http_headers.Authorization")
    if not auth.startswith("Bearer "):
        raise RuntimeError("Authorization header must be Bearer token for OpenAI-compatible auth")

    api_key = auth[len("Bearer ") :].strip()
    if not api_key:
        raise RuntimeError("Bearer token is empty in Codex config")

    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base, api_key


def write_image(data: Any, destination: Path, auth_header: str) -> None:
    b64_json = getattr(data, "b64_json", None)
    if b64_json:
        destination.write_bytes(base64.b64decode(b64_json))
        return

    url = getattr(data, "url", None)
    if url:
        request = urllib.request.Request(str(url), headers={"Authorization": auth_header})
        with urllib.request.urlopen(request, timeout=120) as response:
            destination.write_bytes(response.read())
        return

    raise RuntimeError("Image response had neither b64_json nor url")


def generate_fixture_pack(base_url: str, api_key: str, model: str, size: str, quality: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("vacation_*.jpg"):
        old.unlink()

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=180)
    auth_header = f"Bearer {api_key}"

    manifest_items: list[dict[str, Any]] = []
    for idx, spec in enumerate(PROMPTS, start=1):
        file_name = f"vacation_{idx:02d}.jpg"
        output_path = OUT_DIR / file_name
        prompt = spec["prompt"]

        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
        )
        if not response.data:
            raise RuntimeError(f"No image returned for {spec['id']}")

        write_image(response.data[0], output_path, auth_header)

        manifest_items.append(
            {
                "id": spec["id"],
                "file": file_name,
                "path": f"tests/fixtures/vacation-20/{file_name}",
                "prompt": prompt,
                "tags": spec["tags"],
            }
        )
        print(f"generated {file_name}", flush=True)

    manifest = {
        "dataset": "vacation-20",
        "generator": "openai-image-via-llm-gateway",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gateway_base_url": base_url,
        "model": model,
        "count": len(manifest_items),
        "items": manifest_items,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    base_url, api_key = load_gateway_settings(args.config, args.provider)
    generate_fixture_pack(base_url, api_key, model=args.model, size=args.size, quality=args.quality)
    print(f"Wrote fixture pack to {OUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
