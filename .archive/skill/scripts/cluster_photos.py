#!/usr/bin/env python3
"""
Cluster photos by time and location to detect events
"""

import json
from datetime import datetime


def parse_datetime(dt_str):
    """Parse various datetime formats from EXIF"""
    if not dt_str:
        return None
    formats = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def cluster_by_time(photos, time_threshold_hours=24):
    """Cluster photos within time_threshold of each other"""
    # Sort by date
    sorted_photos = sorted(
        [p for p in photos if p.get("datetime")], key=lambda x: x["datetime"]
    )

    clusters = []
    current_cluster = []

    for photo in sorted_photos:
        if not current_cluster:
            current_cluster.append(photo)
        else:
            time_diff = (
                photo["datetime"] - current_cluster[-1]["datetime"]
            ).total_seconds() / 3600
            if time_diff <= time_threshold_hours:
                current_cluster.append(photo)
            else:
                clusters.append(current_cluster)
                current_cluster = [photo]

    if current_cluster:
        clusters.append(current_cluster)

    return clusters


def main():
    # Load metadata
    with open(".photobook-temp/metadata/photos_metadata.json", "r") as f:
        raw_data = json.load(f)

    # Parse dates
    photos = []
    for item in raw_data:
        dt = parse_datetime(
            item.get("DateTimeOriginal")
            or item.get("CreateDate")
            or item.get("ModifyDate")
        )
        if dt:
            photos.append(
                {
                    "filepath": f"{item.get('Directory', '')}/{item.get('FileName', '')}",
                    "datetime": dt,
                    "gps": {
                        "lat": item.get("GPSLatitude"),
                        "lon": item.get("GPSLongitude"),
                    }
                    if item.get("GPSLatitude")
                    else None,
                    "dimensions": {
                        "width": item.get("ImageWidth"),
                        "height": item.get("ImageHeight"),
                    },
                }
            )

    print(f"Processing {len(photos)} photos with valid dates...")

    # Cluster by time (24 hour threshold)
    clusters = cluster_by_time(photos, time_threshold_hours=24)

    # Format output
    output = []
    for i, cluster in enumerate(clusters):
        dates = [p["datetime"] for p in cluster]
        output.append(
            {
                "id": f"cluster_{i + 1}",
                "photo_count": len(cluster),
                "date_range": {
                    "start": min(dates).isoformat(),
                    "end": max(dates).isoformat(),
                },
                "has_gps": any(p.get("gps") for p in cluster),
                "sample_photos": [p["filepath"] for p in cluster[:5]],
                "all_photos": [p["filepath"] for p in cluster],
            }
        )

    # Save clusters
    with open(".photobook-temp/clusters.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Created {len(output)} clusters")
    print("Saved to .photobook-temp/clusters.json")


if __name__ == "__main__":
    main()
