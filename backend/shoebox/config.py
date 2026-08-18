"""Runtime configuration.

Single source of truth for paths and tunables. Everything is overridable
via environment variables prefixed ``SHOEBOX_``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings.

    Defaults assume a developer running from the repo root. The
    ``data_dir`` is the single place where all runtime artefacts live —
    SQLite DB, originals, derivatives, embeddings.
    """

    model_config = SettingsConfigDict(env_prefix="SHOEBOX_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    db_filename: str = "shoebox.db"

    # Logging.
    log_level: str = "INFO"
    log_to_file: bool = True
    log_filename: str = "shoebox.log"

    # Tier-1 pipeline tunables.
    thumb_small_width: int = 256
    thumb_medium_width: int = 800
    near_duplicate_phash_distance: int = 8

    # Tier-2 pipeline tunables.
    burst_max_seconds: int = 30
    theme_partition_hours: int = 6
    max_location_gap_meters: int = 2000

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / self.log_filename

    def project_dir(self, project_id: str) -> Path:
        return self.data_dir / "projects" / project_id

    def project_originals_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "originals"

    def project_thumbs_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "thumbs"

    def project_medium_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "medium"

    def project_embeddings_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "embeddings"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
