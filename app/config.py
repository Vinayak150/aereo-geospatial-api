"""Explicit, bounded configuration for the local service."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/aereo.db"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_uncompressed_bytes: int = 50 * 1024 * 1024
    max_archive_entries: int = 128
    max_compression_ratio: int = 100
    max_features: int = 5000
    max_coordinates: int = 200_000
    max_xml_elements: int = 100_000
    max_xml_depth: int = 32

    def __post_init__(self) -> None:
        if not self.database_url.startswith("sqlite:"):
            raise ValueError("This submission supports SQLite only.")
        for key, value in vars(self).items():
            if key != "database_url" and (not isinstance(value, int) or value <= 0):
                raise ValueError(f"{key} must be a positive integer")

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        values = {
            name: int(os.environ.get(f"AEREO_{name.upper()}", getattr(defaults, name)))
            for name in vars(defaults)
            if name != "database_url"
        }
        return cls(database_url=os.getenv("AEREO_DATABASE_URL", defaults.database_url), **values)

    def prepare_database_directory(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            location = self.database_url.removeprefix("sqlite:///")
            if location != ":memory:":
                Path(location).parent.mkdir(parents=True, exist_ok=True)
