import hashlib
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Feature, UploadedFile
from app.errors import APIError
from app.services.measurement import measure
from app.services.parsing import parse_file


def process_upload(
    content: bytes, filename: str | None, session: Session, settings: Settings
) -> UploadedFile:
    if not content:
        raise APIError("EMPTY_UPLOAD", "Uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise APIError("UPLOAD_LIMIT", "Uploaded file exceeds configured size limit.", 413)
    if not filename:
        raise APIError("INVALID_FILENAME", "A filename with .kml or .zip extension is required.")
    # Metadata only: the original filename is never used as a storage path.
    safe_name = PurePosixPath(filename.replace("\\", "/")).name
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "_", safe_name)
    if len(safe_name) > 255:
        raise APIError("INVALID_FILENAME", "Filename must be at most 255 characters.")
    extension = PurePosixPath(safe_name).suffix.lower()
    if extension not in {".kml", ".zip"}:
        raise APIError("UNSUPPORTED_FORMAT", "Upload a .kml file or a .zip Shapefile archive.", 415)
    file_format = "kml" if extension == ".kml" else "shapefile"
    dataset = parse_file(content, file_format, settings)
    results = [
        measure(item.geometry, dataset.crs, item.feature_id, index, item.properties)
        for index, item in enumerate(dataset.features)
    ]
    measured = sum(result.status == "MEASURED" for result in results)
    record = UploadedFile(
        id=str(uuid4()),
        filename=safe_name,
        format=file_format,
        crs=dataset.crs.to_string(),
        feature_count=len(results),
        status="COMPLETED",
        uploaded_at=datetime.now(UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        measured_count=measured,
        skipped_count=len(results) - measured,
    )
    # No database mutation until the entire file has been parsed and measured.
    # Context manager rolls back metadata and features together on failure.
    with session.begin():
        session.add(record)
        session.flush()
        session.add_all(
            Feature(file_id=record.id, index=result.index, result=result.model_dump(mode="json"))
            for result in results
        )
    return record
