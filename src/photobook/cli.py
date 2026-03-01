from __future__ import annotations

import argparse
from pathlib import Path

from photobook.project_store import ensure_schema, upsert_thumbnail_records
from photobook.thumbnails import (
    generate_thumbnails,
    iter_photo_paths,
    to_thumbnail_record,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate photo thumbnails")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or folders to thumbnail",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/thumbnails"),
        help="Directory to store thumbnails",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[256, 1024],
        help="One or more max-edge sizes",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(".photobook-temp/project.db"),
        help="SQLite database path for thumbnail records",
    )

    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the API server instead of generating thumbnails",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for the API server",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the API server",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.serve:
        import subprocess

        command = [
            "uvicorn",
            "photobook.api:create_app",
            "--factory",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        subprocess.run(command, check=True)
        return 0
    if not args.paths:
        print("No input paths provided. Pass files/folders or use --serve.")
        return 1
    photos = iter_photo_paths(args.paths)
    if not photos:
        print("No supported images found.")
        return 1

    ensure_schema(args.db_path)
    results = generate_thumbnails(photos, args.cache_dir, args.sizes)
    records = [to_thumbnail_record(result) for result in results]
    upsert_thumbnail_records(args.db_path, records)
    print(f"Generated {len(results)} thumbnails in {args.cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
