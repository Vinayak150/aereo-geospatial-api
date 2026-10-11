from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class FileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    format: Literal["kml", "shapefile"]
    feature_count: int
    crs: str
    status: Literal["COMPLETED"]
    uploaded_at: datetime
    sha256: str
    measured_count: int
    skipped_count: int

    @field_validator("uploaded_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite returns naive datetimes; all stored timestamps are UTC by construction.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class FeatureResult(BaseModel):
    feature_id: str
    index: int
    geometry_type: str | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]
    crs: str
    status: Literal[
        "MEASURED",
        "NO_MEASUREMENT",
        "NULL_GEOMETRY",
        "EMPTY_GEOMETRY",
        "INVALID_GEOMETRY",
        "UNSUPPORTED_GEOMETRY",
        "OUTSIDE_SUPPORTED_EXTENT",
        "TRANSFORMATION_FAILED",
    ]
    reason: str | None = None
    area_m2: float | None = None
    length_m: float | None = None
    measurement_crs: str | None = None
    method: str | None = None
    warnings: list[str] = []


class Measurements(BaseModel):
    file_id: UUID
    total: int
    offset: int
    limit: int
    features: list[FeatureResult]
