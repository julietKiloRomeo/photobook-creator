from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from photobook.project_store import (
    add_cluster_photos,
    clear_clusters,
    create_cluster,
    list_photo_paths,
)


@dataclass(frozen=True)
class ClusteredPhoto:
    photo_path: str
    taken_at: datetime


@dataclass(frozen=True)
class ClusterWindow:
    start_at: datetime
    end_at: datetime
    photos: list[ClusteredPhoto]


def parse_taken_at(photo_path: str) -> datetime:
    timestamp = Path(photo_path).stem.split("_", 1)[0]
    return datetime.strptime(timestamp, "%Y%m%dT%H%M%S")


def build_time_clusters(
    photos: list[ClusteredPhoto], window_minutes: int
) -> list[ClusterWindow]:
    if not photos:
        return []
    ordered = sorted(photos, key=lambda photo: photo.taken_at)
    clusters: list[ClusterWindow] = []
    current: list[ClusteredPhoto] = []
    window = timedelta(minutes=window_minutes)
    cluster_start: datetime | None = None
    for photo in ordered:
        if not current:
            current = [photo]
            cluster_start = photo.taken_at
            continue
        if photo.taken_at - (cluster_start or photo.taken_at) <= window:
            current.append(photo)
            continue
        clusters.append(
            ClusterWindow(
                start_at=current[0].taken_at,
                end_at=current[-1].taken_at,
                photos=current,
            )
        )
        current = [photo]
        cluster_start = photo.taken_at
    if current:
        clusters.append(
            ClusterWindow(
                start_at=current[0].taken_at,
                end_at=current[-1].taken_at,
                photos=current,
            )
        )
    return clusters


def cluster_photos_by_time(db_path: Path, window_minutes: int = 60) -> int:
    paths = list_photo_paths(db_path)
    photos = [ClusteredPhoto(path, parse_taken_at(path)) for path in paths]
    clusters = build_time_clusters(photos, window_minutes)
    clear_clusters(db_path)
    for index, cluster in enumerate(clusters, start=1):
        cluster_id = create_cluster(
            db_path,
            name=f"Event {index}",
            start_at=cluster.start_at.isoformat(),
            end_at=cluster.end_at.isoformat(),
            kind="event",
        )
        add_cluster_photos(
            db_path,
            cluster_id,
            [
                {
                    "photo_path": photo.photo_path,
                    "rank": position,
                    "role": "member",
                }
                for position, photo in enumerate(cluster.photos, start=1)
            ],
        )
    return len(clusters)
