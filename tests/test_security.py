import asyncio
import io
import stat
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.config import Settings
from app.db import Feature, UploadedFile
from app.main import create_app
from app.middleware import BodyLimitMiddleware
from tests.conftest import kml_bytes, zip_bytes
from tests.test_api import post


@pytest.mark.parametrize(
    "name,content,status,code",
    [
        ("a.kml", b"", 422, "EMPTY_UPLOAD"),
        ("a.txt", b"abc", 415, "UNSUPPORTED_FORMAT"),
        ("a.zip", b"not zip", 422, "INVALID_ARCHIVE"),
        ("a.kml", b"not xml", 422, "INVALID_KML"),
        ("a.kml", b"<html/>", 422, "INVALID_KML"),
        ("a.kml", b"\xff\xfeBAD", 422, "INVALID_KML"),
        ("a.kml", kml_bytes(""), 422, "EMPTY_DATASET"),
        (
            "a.kml",
            b'<!DOCTYPE kml [<!ENTITY x SYSTEM "file:///etc/passwd">]><kml>&x;</kml>',
            422,
            "INVALID_KML",
        ),
        (
            "a.kml",
            kml_bytes(
                "<NetworkLink><Link><href>http://localhost/secret</href></Link></NetworkLink>"
            ),
            422,
            "UNSUPPORTED_KML",
        ),
        ("a.kml", kml_bytes("<Placemark><Model/></Placemark>"), 422, "UNSUPPORTED_KML"),
        ("a" * 256 + ".kml", b"x", 422, "INVALID_FILENAME"),
    ],
)
def test_rejected_content(client, name, content, status, code):
    response = post(client, content, name)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(UploadedFile)) == 0


@pytest.mark.parametrize(
    "name",
    [
        "../evil",
        "/absolute",
        "C:/windows",
        "nested/../../escape",
        "nested\\windows",
        "./../escape",
        "bad\x01name",
    ],
)
def test_archive_paths(client, shape_entries, name):
    shape_entries[name] = b"attack"
    response = post(client, zip_bytes(shape_entries), "a.zip")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSAFE_ARCHIVE"


@pytest.mark.parametrize(
    "suffix,code",
    [
        (".shp", "AMBIGUOUS_DATASET"),
        (".shx", "MISSING_COMPANION"),
        (".dbf", "MISSING_COMPANION"),
        (".prj", "MISSING_CRS"),
    ],
)
def test_missing_companions(client, shape_entries, suffix, code):
    filtered = {name: data for name, data in shape_entries.items() if not name.endswith(suffix)}
    response = post(client, zip_bytes(filtered), "a.zip")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_ambiguous_dataset_and_duplicates(client, shape_entries):
    extras = dict(shape_entries)
    extras.update({name.replace("survey", "other"): data for name, data in shape_entries.items()})
    assert post(client, zip_bytes(extras), "a.zip").json()["error"]["code"] == "AMBIGUOUS_DATASET"
    extras = dict(shape_entries)
    extras["NESTED/SURVEY.SHP"] = b"duplicate"
    assert post(client, zip_bytes(extras), "a.zip").json()["error"]["code"] == "AMBIGUOUS_ARCHIVE"


def test_case_insensitive_companions(client, shape_entries):
    entries = {name.upper(): content for name, content in shape_entries.items()}
    assert post(client, zip_bytes(entries), "a.zip").status_code == 201


def test_symlink_archive(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        entry = zipfile.ZipInfo("link.shp")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, "/etc/passwd")
    response = post(client, buffer.getvalue(), "a.zip")
    assert response.json()["error"]["code"] == "UNSAFE_ARCHIVE"


def test_archive_bomb_and_nested_archive(client, shape_entries):
    shape_entries["large.txt"] = b"a" * 200_000
    assert post(client, zip_bytes(shape_entries), "a.zip").status_code == 413
    del shape_entries["large.txt"]
    shape_entries["nested.zip"] = b"fake archive"
    assert (
        post(client, zip_bytes(shape_entries), "a.zip").json()["error"]["code"] == "UNSAFE_ARCHIVE"
    )


@pytest.mark.parametrize(
    "field,limit", [("max_archive_entries", 1), ("max_uncompressed_bytes", 10)]
)
def test_archive_resource_limits(config, shape_zip, field, limit):
    with TestClient(create_app(replace(config, **{field: limit}))) as client:
        assert post(client, shape_zip, "a.zip").status_code == 413


def test_malformed_crs_and_wrong_signature(client, shape_entries):
    shape_entries["nested/survey.prj"] = b"not a coordinate reference system"
    response = post(client, zip_bytes(shape_entries), "a.zip")
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"MISSING_CRS", "INVALID_CRS", "INVALID_SHAPEFILE"}
    shape_entries["nested/survey.shp"] = b"not a shapefile"
    assert (
        post(client, zip_bytes(shape_entries), "a.zip").json()["error"]["code"]
        == "INVALID_SHAPEFILE"
    )


@pytest.mark.parametrize(
    "field,limit",
    [("max_features", 2), ("max_coordinates", 2), ("max_xml_elements", 2), ("max_xml_depth", 2)],
)
def test_kml_resource_limits(config, kml, field, limit):
    with TestClient(create_app(replace(config, **{field: limit}))) as client:
        assert post(client, kml).status_code == 413


def test_upload_limit(config, kml):
    with TestClient(create_app(replace(config, max_upload_bytes=32))) as client:
        assert post(client, kml).status_code == 413
        assert post(client, b"a" * 70_000).status_code == 413


def test_request_stream_limit_without_content_length():
    reached_app = False

    async def endpoint(scope, receive, send):
        nonlocal reached_app
        reached_app = True

    async def exercise():
        messages = iter(
            [
                {"type": "http.request", "body": b"abc", "more_body": True},
                {"type": "http.request", "body": b"def", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        await BodyLimitMiddleware(endpoint, 5)({"type": "http", "headers": []}, receive, send)
        return sent

    sent = asyncio.run(exercise())
    assert sent[0]["status"] == 413
    assert not reached_app


def test_temporary_cleanup_on_success_and_failure(client, shape_zip, shape_entries, tmp_path):
    from tempfile import TemporaryDirectory

    created = []

    def tracked(*args, **kwargs):
        temporary = TemporaryDirectory(*args, dir=tmp_path, **kwargs)
        created.append(Path(temporary.name))
        return temporary

    with patch("app.services.parsing.TemporaryDirectory", side_effect=tracked):
        assert post(client, shape_zip, "a.zip").status_code == 201
        shape_entries["nested/survey.shp"] = b"bad"
        assert post(client, zip_bytes(shape_entries), "a.zip").status_code == 422
    assert len(created) == 2 and all(not path.exists() for path in created)


def test_transaction_rolls_back_metadata_and_features(config, kml):
    def fail_insert(mapper, connection, target):
        raise RuntimeError("injected write failure")

    event.listen(Feature, "before_insert", fail_insert)
    try:
        with TestClient(create_app(config), raise_server_exceptions=False) as client:
            assert post(client, kml).status_code == 500
            with client.app.state.session_factory() as session:
                assert session.scalar(select(func.count()).select_from(UploadedFile)) == 0
                assert session.scalar(select(func.count()).select_from(Feature)) == 0
    finally:
        event.remove(Feature, "before_insert", fail_insert)


def test_settings_reject_invalid_limits():
    with pytest.raises(ValueError):
        Settings(max_features=0)
    with pytest.raises(ValueError):
        Settings(database_url="postgresql://host/database")
