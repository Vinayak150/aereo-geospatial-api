"""Real companion-file mutations and ambiguous KML attributes must not lose data."""

import struct

import pyogrio.raw
import pytest
from sqlalchemy import func, select

from app.db import Feature, UploadedFile
from tests.conftest import kml_bytes, zip_bytes
from tests.test_api import post


@pytest.fixture
def two_feature_entries(shape_entries, tmp_path):
    # Extend the existing real-GDAL fixture; retain its archive utility/layout.
    path = tmp_path / "source/survey.shp"
    meta, _, geometries, columns = pyogrio.raw.read(path, return_fids=True)
    columns[0][0], columns[1][0] = "second", 8
    pyogrio.raw.write(
        path,
        geometries,
        columns,
        list(meta["fields"]),
        driver="ESRI Shapefile",
        geometry_type="Polygon",
        crs="EPSG:32643",
        append=True,
    )
    return {f"nested/{p.name}": p.read_bytes() for p in path.parent.iterdir()}


def no_records(client):
    with client.app.state.session_factory() as session:
        for model in (UploadedFile, Feature):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("declared", [1, 3])
def test_dbf_count_mismatch_rejected_without_persistence(client, two_feature_entries, declared):
    key = "nested/survey.dbf"
    original = two_feature_entries[key]
    assert struct.unpack_from("<I", original, 4)[0] == 2
    mutated = bytearray(original)
    struct.pack_into("<I", mutated, 4, declared)
    assert mutated[:4] == original[:4] and mutated[8:] == original[8:]
    two_feature_entries[key] = bytes(mutated)
    response = post(client, zip_bytes(two_feature_entries), "private-name.zip")
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "INVALID_SHAPEFILE",
            "message": "Shapefile geometry, index and attribute records are inconsistent.",
        }
    }
    no_records(client)


@pytest.mark.parametrize(
    "damage", ["short_index", "index_size", "index_offset", "index_length", "dbf_row", "flag"]
)
def test_incomplete_record_correspondence_is_rejected(client, two_feature_entries, damage):
    shx = bytearray(two_feature_entries["nested/survey.shx"])
    dbf = bytearray(two_feature_entries["nested/survey.dbf"])
    header, width = struct.unpack_from("<HH", dbf, 8)
    if damage == "short_index":
        shx = shx[:50]
    elif damage == "index_size":
        struct.pack_into(">I", shx, 24, 54)
    elif damage == "index_offset":
        struct.pack_into(">I", shx, 100, 2**30)
    elif damage == "index_length":
        struct.pack_into(">I", shx, 104, 2)
    elif damage == "dbf_row":
        dbf = dbf[: header + width]
    else:
        dbf[header] = ord("?")
    two_feature_entries["nested/survey.shx"] = bytes(shx)
    two_feature_entries["nested/survey.dbf"] = bytes(dbf)
    response = post(client, zip_bytes(two_feature_entries), "broken.zip")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SHAPEFILE"
    no_records(client)


@pytest.mark.parametrize(
    "deleted,omit_eof,expected_ids",
    [((), True, ["0", "1"]), ((0,), False, ["1"]), ((1,), True, ["0"]), ((0, 1), False, [])],
)
def test_deleted_dbf_rows_and_optional_eof_are_respected(
    client, two_feature_entries, deleted, omit_eof, expected_ids
):
    dbf = bytearray(two_feature_entries["nested/survey.dbf"])
    header, width = struct.unpack_from("<HH", dbf, 8)
    for index in deleted:
        dbf[header + index * width] = ord("*")
    assert dbf[-1] == 0x1A
    two_feature_entries["nested/survey.dbf"] = bytes(dbf[:-1] if omit_eof else dbf)
    response = post(client, zip_bytes(two_feature_entries), "deleted.zip")
    if not expected_ids:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "EMPTY_DATASET"
        no_records(client)
        return
    assert response.status_code == 201, response.text
    assert response.json()["feature_count"] == len(expected_ids)
    features = client.get(f"/api/files/{response.json()['id']}/measurements/").json()["features"]
    assert [f["feature_id"] for f in features] == expected_ids
    assert [f["properties"]["site"] for f in features] == [
        "mine" if fid == "0" else "second" for fid in expected_ids
    ]


def test_indexed_geometry_can_follow_obsolete_shp_block(client, two_feature_entries):
    # Editing a variable-sized shape can leave the old block until REPACK.
    shp = bytearray(two_feature_entries["nested/survey.shp"])
    shx = bytearray(two_feature_entries["nested/survey.shx"])
    offset, length = struct.unpack_from(">II", shx, 100)
    record = shp[offset * 2 : offset * 2 + 8 + length * 2]
    struct.pack_into(">I", shx, 100, len(shp) // 2)
    shp.extend(record)
    struct.pack_into(">I", shp, 24, len(shp) // 2)
    two_feature_entries["nested/survey.shp"] = bytes(shp)
    two_feature_entries["nested/survey.shx"] = bytes(shx)
    response = post(client, zip_bytes(two_feature_entries), "edited.zip")
    assert response.status_code == 201, response.text
    assert response.json()["feature_count"] == 2


def test_reader_omission_cannot_bypass_active_record_check(
    client, two_feature_entries, monkeypatch
):
    read = pyogrio.raw.read

    def omit(*args, **kwargs):
        meta, ids, geometries, columns = read(*args, **kwargs)
        return meta, ids[:1], geometries[:1], [column[:1] for column in columns]

    monkeypatch.setattr("app.services.parsing.pyogrio.raw.read", omit)
    response = post(client, zip_bytes(two_feature_entries), "reader-omission.zip")
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "INVALID_SHAPEFILE",
            "message": "Reader did not return every active Shapefile record.",
        }
    }
    no_records(client)


@pytest.mark.parametrize(
    "attributes",
    [
        '<Data name="site"><value>first</value></Data><Data name="site"><value>second</value></Data>',
        '<SchemaData schemaUrl="#a"><SimpleData name="site">first</SimpleData><SimpleData name="site">second</SimpleData></SchemaData>',
        '<SchemaData schemaUrl="#a"><SimpleData name="site">first</SimpleData></SchemaData><SchemaData schemaUrl="#b"><SimpleData name="site">second</SimpleData></SchemaData>',
        '<Data name="site"><value>first</value></Data><SchemaData schemaUrl="#a"><SimpleData name="site">second</SimpleData></SchemaData>',
    ],
)
def test_colliding_extended_data_names_reject_entire_upload(client, attributes):
    point = "<Point><coordinates>77,13</coordinates></Point>"
    content = kml_bytes(
        f"<Placemark>{point}</Placemark>"
        f"<Placemark><ExtendedData>{attributes}</ExtendedData>{point}</Placemark>"
    )
    response = post(client, content, "private.kml")
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "INVALID_KML",
            "message": "ExtendedData names must be unique within each feature.",
        }
    }
    no_records(client)
