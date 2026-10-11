from dataclasses import replace

import numpy as np
import pyogrio.raw
import pytest
from fastapi.testclient import TestClient
from pyproj import CRS
from pyproj.exceptions import ProjError
from shapely import to_wkb
from shapely.geometry import LineString, MultiPolygon, box
from sqlalchemy import func, select

from app.db import UploadedFile
from app.main import create_app
from app.services.measurement import measure
from tests.conftest import kml_bytes, zip_bytes
from tests.test_api import post

RING = (
    "<LinearRing><coordinates>77,13 77.01,13 77.01,13.01 77,13.01 77,13</coordinates></LinearRing>"
)


@pytest.mark.parametrize(
    "geometry",
    [
        "<Polygon>" + f"<outerBoundaryIs>{RING}</outerBoundaryIs>" * 2 + "</Polygon>",
        "<LineString><coordinates>77,13 77.01,13</coordinates><coordinates>77,13 77.5,13</coordinates></LineString>",
        f"<Polygon><outerBoundaryIs>{RING}{RING}</outerBoundaryIs></Polygon>",
        "<Point><coordinates>77,13</coordinates><coordinates>78,14</coordinates></Point>",
    ],
)
def test_ambiguous_kml_geometry_is_rejected_without_partial_record(client, geometry):
    response = post(client, kml_bytes(f"<Placemark>{geometry}</Placemark>"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_KML"
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(UploadedFile)) == 0


@pytest.mark.parametrize(
    "wkt,expected_code",
    [
        (CRS.from_epsg(4978).to_wkt(), "MISSING_CRS"),
        (
            'LOCAL_CS["Local engineering",LOCAL_DATUM["Local",0],UNIT["metre",1],AXIS["Easting",EAST],AXIS["Northing",NORTH]]',
            "UNSUPPORTED_CRS",
        ),
    ],
)
def test_unsupported_shapefile_crs_is_safely_rejected(client, shape_entries, wkt, expected_code):
    # GDAL drops geocentric .prj metadata, but preserves an engineering CRS.
    # Neither is silently assumed to be geographic or projected survey data.
    shape_entries["nested/survey.prj"] = wkt.encode()
    response = post(client, zip_bytes(shape_entries), "geocentric.zip")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.parametrize("limit", ["max_features", "max_coordinates"])
def test_real_multipart_shapefile_limits_are_atomic(config, tmp_path, limit):
    source = tmp_path / "complex"
    source.mkdir()
    multi = MultiPolygon(
        [box(500000 + n * 20, 1400000, 500010 + n * 20, 1400010) for n in range(5)]
    )
    pyogrio.raw.write(
        source / "parts.shp",
        to_wkb(np.array([multi, multi], dtype=object)),
        [np.array([1, 2])],
        ["number"],
        driver="ESRI Shapefile",
        geometry_type="MultiPolygon",
        crs="EPSG:32643",
    )
    content = zip_bytes({p.name: p.read_bytes() for p in source.iterdir()})
    with TestClient(
        create_app(replace(config, **{limit: 1 if limit == "max_features" else 20}))
    ) as api:
        response = post(api, content, "complex.zip")
        assert response.status_code == 413
        assert response.json()["error"]["code"] == (
            "FEATURE_LIMIT" if limit == "max_features" else "GEOMETRY_LIMIT"
        )
        with api.app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(UploadedFile)) == 0


def test_unavailable_transform_has_no_fallback_number(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ProjError("Required grid is unavailable: private diagnostic")

    monkeypatch.setattr("app.services.measurement.Transformer.from_crs", unavailable)
    result = measure(LineString([(77, 13), (77.01, 13)]), CRS.from_epsg(4326), "line", 0, {})
    assert result.status == "TRANSFORMATION_FAILED"
    assert result.length_m is None and result.measurement_crs is None
    assert "private" not in result.model_dump_json()
