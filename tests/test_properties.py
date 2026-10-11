"""Metamorphic checks with explicit shared-projection preconditions.

The metre-coordinate constructions stay near UTM 43N's central meridian, use
binary-exact quarter-metre holes and at most 500 m sides. Additivity tolerances
of 1e-6 m² allow numerical roundoff at million-metre coordinate magnitudes;
they are not survey accuracy bounds. Reversal uses the same vertices/projection.
"""

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from pyproj import CRS
from shapely import reverse
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from app.config import Settings
from app.main import create_app
from app.services.measurement import measure
from tests.conftest import kml_bytes
from tests.test_api import post

RUN = settings(max_examples=40, derandomize=True, database=None, deadline=None)
METRIC, WGS = CRS.from_epsg(32643), CRS.from_epsg(4326)
SIZE = st.integers(4, 500)
X, Y = 500000, 1400000


def measured(geometry, crs=METRIC):
    result = measure(geometry, crs, "property", 0, {})
    assert result.status == "MEASURED"
    return result


@RUN
@given(width=SIZE, height=SIZE)
def test_polygon_ring_reversal_preserves_area(width, height):
    # Geographic vertices exercise actual reprojection, including a hole.
    outer = box(77, 13, 77 + width / 100000, 13 + height / 100000)
    hole = box(77 + width / 400000, 13 + height / 400000, 77 + width / 200000, 13 + height / 200000)
    polygon = Polygon(outer.exterior.coords, [hole.exterior.coords])
    assert polygon.is_valid
    forward, backward = measured(polygon, WGS), measured(reverse(polygon), WGS)
    assert forward.measurement_crs == backward.measurement_crs
    assert forward.area_m2 == pytest.approx(backward.area_m2, rel=1e-12, abs=1e-6)


@RUN
@given(width=SIZE, height=SIZE)
def test_hole_area_equals_difference_in_same_projected_crs(width, height):
    exterior = box(X, Y, X + width, Y + height)
    hole = box(X + width / 4, Y + height / 4, X + width / 2, Y + height / 2)
    polygon = Polygon(exterior.exterior.coords, [hole.exterior.coords])
    results = [measured(item) for item in (exterior, hole, polygon)]
    assert {item.measurement_crs for item in results} == {"EPSG:32643"}
    assert results[2].area_m2 == pytest.approx(
        results[0].area_m2 - results[1].area_m2, abs=1e-6, rel=0
    )


@RUN
@given(width=SIZE, height=SIZE, gap=st.integers(1, 100))
def test_multipart_area_equals_sum_when_selected_crs_matches(width, height, gap):
    first = box(X, Y, X + width, Y + height)
    second = box(X + width + gap, Y, X + 2 * width + gap, Y + height)
    multi = MultiPolygon([first, second])
    assert multi.is_valid
    results = [measured(item) for item in (first, second, multi)]
    assert {item.measurement_crs for item in results} == {"EPSG:32643"}
    assert results[2].area_m2 == pytest.approx(
        results[0].area_m2 + results[1].area_m2, abs=1e-6, rel=0
    )


@RUN
@given(
    vertices=st.lists(
        st.tuples(st.integers(0, 100), st.integers(0, 100)), min_size=2, max_size=12, unique=True
    )
)
def test_line_reversal_preserves_length(vertices):
    line = LineString([(77 + x / 10000, 13 + y / 10000) for x, y in vertices])
    forward, backward = measured(line, WGS), measured(reverse(line), WGS)
    assert forward.measurement_crs == backward.measurement_crs
    assert forward.length_m == pytest.approx(backward.length_m, rel=1e-12, abs=1e-8)


@RUN
@given(order=st.permutations((0, 1, 2)), offset=st.integers(0, 100))
def test_http_feature_processing_order_does_not_change_results(order, offset):
    longitude = 77 + offset / 10000
    features = [
        f'<Placemark id="line"><LineString><coordinates>{longitude},13 {longitude + 0.001},13.001</coordinates></LineString></Placemark>',
        f'<Placemark id="point"><Point><coordinates>{longitude},13</coordinates></Point></Placemark>',
        '<Placemark id="south"><LineString><coordinates>18.4,-33.9 18.401,-33.899</coordinates></LineString></Placemark>',
    ]
    with TestClient(create_app(Settings(database_url="sqlite:///:memory:"))) as api:
        results = []
        for sequence in (range(3), order):
            response = post(api, kml_bytes("".join(features[i] for i in sequence)))
            assert response.status_code == 201
            page = api.get(f"/api/files/{response.json()['id']}/measurements/").json()
            results.append(
                {
                    item["feature_id"]: (
                        item["area_m2"],
                        item["length_m"],
                        item["measurement_crs"],
                        item["status"],
                    )
                    for item in page["features"]
                }
            )
        assert results[0] == results[1]
