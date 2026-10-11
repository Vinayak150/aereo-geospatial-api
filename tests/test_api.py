import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import Feature, UploadedFile
from app.main import create_app
from app.schemas import FileInfo, Measurements
from tests.conftest import kml_bytes


def post(client, content, name="survey.kml"):
    return client.post("/api/files/", files={"file": (name, content, "application/octet-stream")})


def test_kml_contract(client, kml):
    response = post(client, kml)
    assert response.status_code == 201, response.text
    data = response.json()
    FileInfo.model_validate(data)
    assert data["feature_count"] == 4
    assert data["crs"] == "EPSG:4326"
    assert data["status"] == "COMPLETED"
    assert data["measured_count"] == 2
    assert data["skipped_count"] == 2
    identifier = data["id"]
    metadata = client.get(f"/api/files/{identifier}/").json()
    assert metadata["id"] == identifier
    result = client.get(f"/api/files/{identifier}/measurements/")
    assert result.status_code == 200
    Measurements.model_validate(result.json())
    features = result.json()["features"]
    assert [f["index"] for f in features] == [0, 1, 2, 3]
    assert [f["feature_id"] for f in features] == ["parcel-1", "road", "marker", "null"]
    assert features[0]["properties"]["extended_data"] == {"owner": "Aereo", "code": "42"}
    assert features[0]["geometry"]["type"] == "Polygon"
    assert features[0]["area_m2"] > 10000
    assert features[1]["length_m"] > 100
    assert features[2]["status"] == "NO_MEASUREMENT"
    assert features[3]["status"] == "NULL_GEOMETRY"
    assert "NaN" not in result.text and "Infinity" not in result.text


def test_shapefile_real_roundtrip(client, shape_zip):
    response = post(client, shape_zip, "SURVEY.ZIP")
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["format"] == "shapefile" and data["crs"] == "EPSG:32643"
    feature = client.get(f"/api/files/{data['id']}/measurements/").json()["features"][0]
    assert feature["area_m2"] == pytest.approx(200, abs=1e-6)
    assert feature["feature_id"] == "0"
    assert feature["properties"] == {"site": "mine", "number": 7}
    assert feature["measurement_crs"] == "EPSG:32643"


def test_restart_persistence(config, kml):
    with TestClient(create_app(config)) as first:
        data = post(first, kml).json()
        expected = first.get(f"/api/files/{data['id']}/measurements/").json()
    with TestClient(create_app(config)) as second:
        assert second.get(f"/api/files/{data['id']}/").status_code == 200
        assert second.get(f"/api/files/{data['id']}/measurements/").json() == expected


def test_pagination_and_unknown_ids(client, kml):
    identifier = post(client, kml).json()["id"]
    endpoint = f"/api/files/{identifier}/measurements/"
    page = client.get(endpoint, params={"offset": 1, "limit": 2}).json()
    assert page["total"] == 4 and len(page["features"]) == 2
    assert [f["index"] for f in page["features"]] == [1, 2]
    assert client.get(endpoint, params={"offset": 999}).json()["features"] == []
    for params in ({"offset": -1}, {"limit": 0}, {"limit": 501}, {"limit": "abc"}):
        assert client.get(endpoint, params=params).status_code == 422
    for path in (f"/api/files/{uuid4()}/", f"/api/files/{uuid4()}/measurements/"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "FILE_NOT_FOUND"
    assert client.get("/api/files/not-a-uuid/").status_code == 422


def test_repeat_upload_and_concurrency(client, kml):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: post(client, kml), range(4)))
    assert all(r.status_code == 201 for r in responses)
    assert len({r.json()["id"] for r in responses}) == 4
    assert len({r.json()["sha256"] for r in responses}) == 1


def test_invalid_feature_isolated(client):
    content = kml_bytes("""<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
    77,13 77.001,13.001 77.001,13 77,13.001 77,13
    </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
    <Placemark><LineString><coordinates>77,13 77.001,13</coordinates></LineString></Placemark>""")
    response = post(client, content)
    assert response.status_code == 201, response.text
    features = client.get(f"/api/files/{response.json()['id']}/measurements/").json()["features"]
    assert [f["status"] for f in features] == ["INVALID_GEOMETRY", "MEASURED"]


def test_failures_leave_no_records(client, kml, monkeypatch):
    import app.services.files as service

    original = service.measure
    count = 0

    def fail_second(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("private filesystem detail")
        return original(*args)

    monkeypatch.setattr(service, "measure", fail_second)
    with TestClient(client.app, raise_server_exceptions=False) as api:
        response = post(api, kml)
        assert response.status_code == 500
        assert "private" not in response.text
        with api.app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(UploadedFile)) == 0
            assert session.scalar(select(func.count()).select_from(Feature)) == 0


def test_openapi_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/api/files/",
        "/api/files/{id}/",
        "/api/files/{id}/measurements/",
        "/health",
    }
    upload = schema["paths"]["/api/files/"]["post"]
    assert "multipart/form-data" in upload["requestBody"]["content"]
    assert "201" in upload["responses"]
    assert upload["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "ErrorResponse"
    )
    json.dumps(schema, allow_nan=False)


@pytest.mark.parametrize(
    "files,data",
    [
        ({}, None),
        ({"wrong": ("x.kml", b"x")}, None),
        ({"file": ("x.kml", b"x")}, {"extra": "ignored?"}),
    ],
)
def test_wrong_request_fields(client, files, data):
    response = client.post("/api/files/", files=files, data=data)
    assert response.status_code == 422
    assert "error" in response.json()


def test_original_filename_is_metadata_only(client, kml):
    response = post(client, kml, "../../private/survey.kml")
    assert response.status_code == 201
    assert response.json()["filename"] == "survey.kml"
