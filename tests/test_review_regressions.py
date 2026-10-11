"""Regressions for defects found through adversarial review, not mocks."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def review_client(tmp_path):
    application = create_app(Settings(database_url=f"sqlite:///{tmp_path}/review.sqlite"))
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client


def kml(geometry: str) -> bytes:
    return (
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark>' + geometry + "</Placemark></kml>"
    ).encode()


@pytest.mark.parametrize(
    "geometry",
    [
        "<Point><coordinates>bad,13</coordinates></Point>",
        "<LineString><coordinates>77,13</coordinates></LineString>",
    ],
)
def test_invalid_geometry_parser_exceptions_are_safe_client_errors(review_client, geometry):
    response = review_client.post("/api/files/", files={"file": ("broken.kml", kml(geometry))})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_KML"
    assert "Traceback" not in response.text
    assert "coordinates>" not in response.text


def test_multiple_direct_geometries_cannot_silently_drop_a_geometry(review_client):
    body = kml(
        "<Point><coordinates>77,13</coordinates></Point>"
        "<LineString><coordinates>77,13 77.1,13.1</coordinates></LineString>"
    )
    response = review_client.post("/api/files/", files={"file": ("ambiguous.kml", body)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_KML"


def test_broken_deflate_stream_is_a_safe_archive_error(review_client):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for suffix in ("shp", "shx", "dbf", "prj"):
            archive.writestr(f"dataset.{suffix}", b"abcdefgh" * 10)
    content = bytearray(stream.getvalue())
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entry = archive.infolist()[0]
        compressed_start = (
            entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        )
    content[compressed_start] = 0xFF  # Invalid DEFLATE block type, with a valid ZIP directory.
    response = review_client.post("/api/files/", files={"file": ("broken.zip", bytes(content))})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARCHIVE"


def test_metadata_is_identical_on_upload_and_subsequent_retrieval(review_client):
    body = kml("<Point><coordinates>77,13</coordinates></Point>")
    response = review_client.post("/api/files/", files={"file": ("point.kml", body)})
    assert response.status_code == 201
    uploaded = response.json()
    retrieved = review_client.get(f"/api/files/{uploaded['id']}/")
    assert retrieved.status_code == 200
    assert retrieved.json() == uploaded
    assert uploaded["uploaded_at"].endswith("Z")
