"""Independent analytic and ellipsoidal checks of the measurement policy.

Analytic fixtures use zone 43's central meridian in metres. Geographic comparisons
allow 0.2% length / 0.4% area error: these conservatively cover UTM scale distortion
within 3.5 degrees of the selected central meridian, not floating-point noise.
"""

import warnings

import pytest
from pyproj import CRS, Geod
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.services.measurement import finite_json, measure

METRIC = CRS.from_epsg(32643)
WGS84 = CRS.from_epsg(4326)
GEOD = Geod(ellps="WGS84")
X, Y = 500_000, 1_400_000


def result_for(geometry, crs=METRIC):
    return measure(geometry, crs, "source-feature-7", 7, {"name": "Survey", "value": 42})


@pytest.mark.parametrize(
    ("geometry", "expected"),
    [
        (box(X, Y, X + 10, Y + 20), 200),
        (
            Polygon(
                [(X, Y), (X + 10, Y), (X + 10, Y + 20), (X, Y + 20)],
                [[(X + 2, Y + 2), (X + 4, Y + 2), (X + 4, Y + 7), (X + 2, Y + 7)]],
            ),
            190,
        ),
        (MultiPolygon([box(X, Y, X + 10, Y + 10), box(X + 20, Y, X + 25, Y + 5)]), 125),
    ],
)
def test_analytic_metric_area_including_holes_and_multipart(geometry, expected):
    result = result_for(geometry)
    assert result.status == "MEASURED"
    assert result.area_m2 == pytest.approx(expected, abs=1e-8)
    assert result.length_m is None
    assert result.measurement_crs == "EPSG:32643"
    assert result.method == "planar_local_utm"


@pytest.mark.parametrize(
    ("geometry", "expected"),
    [
        (LineString([(X, Y), (X + 3, Y + 4)]), 5),
        (
            MultiLineString([[(X, Y), (X + 3, Y + 4)], [(X, Y + 10), (X + 6, Y + 18)]]),
            15,
        ),
    ],
)
def test_analytic_metric_lengths(geometry, expected):
    result = result_for(geometry)
    assert result.status == "MEASURED"
    assert result.length_m == pytest.approx(expected, abs=1e-9)
    assert result.area_m2 is None


@pytest.mark.parametrize("units,metres_per_unit", [("ft", 0.3048), ("us-ft", 1200 / 3937)])
def test_projected_feet_are_converted_to_metres(units, metres_per_unit):
    source = CRS.from_proj4(f"+proj=utm +zone=43 +datum=WGS84 +units={units} +no_defs")
    rectangle = box(
        X / metres_per_unit,
        Y / metres_per_unit,
        (X + 10) / metres_per_unit,
        (Y + 20) / metres_per_unit,
    )
    result = result_for(rectangle, source)
    assert result.status == "MEASURED"
    assert result.area_m2 == pytest.approx(200, abs=1e-6)
    line = LineString(
        [
            (X / metres_per_unit, Y / metres_per_unit),
            ((X + 3) / metres_per_unit, (Y + 4) / metres_per_unit),
        ]
    )
    assert result_for(line, source).length_m == pytest.approx(5, abs=1e-8)


@pytest.mark.parametrize(
    ("longitude", "latitude", "expected_crs"),
    [
        (77.6, 12.9, "EPSG:32643"),
        (18.4, -33.9, "EPSG:32734"),
        (5.999, 0, "EPSG:32632"),
        (-177, 60, "EPSG:32601"),
        (179.99, 10, "EPSG:32660"),
    ],
)
def test_geographic_length_matches_independent_ellipsoid_reference(
    longitude, latitude, expected_crs
):
    endpoint = (longitude + 0.002, latitude + 0.003)
    geometry = LineString([(longitude, latitude), endpoint])
    expected = GEOD.inv(longitude, latitude, *endpoint)[2]
    result = result_for(geometry, WGS84)
    assert result.status == "MEASURED"
    assert result.length_m == pytest.approx(expected, rel=0.002)
    assert result.measurement_crs == expected_crs


@pytest.mark.parametrize("longitude,latitude", [(77.6, 12.9), (18.4, -33.9), (5.995, 0)])
def test_geographic_polygon_area_matches_independent_ellipsoid_reference(longitude, latitude):
    geometry = box(longitude, latitude, longitude + 0.01, latitude + 0.01)
    expected = abs(GEOD.geometry_area_perimeter(geometry)[0])
    result = result_for(geometry, WGS84)
    assert result.status == "MEASURED"
    assert result.area_m2 == pytest.approx(expected, rel=0.004)


def test_original_geometry_and_feature_attributes_preserved():
    geometry = LineString([(77.6, 12.9), (77.601, 12.901)])
    result = result_for(geometry, WGS84)
    assert result.feature_id == "source-feature-7"
    assert result.index == 7
    assert result.properties == {"name": "Survey", "value": 42}
    assert result.geometry["coordinates"] == tuple(geometry.coords)
    assert result.crs == "EPSG:4326"


def test_altitude_preserved_but_excluded_from_horizontal_length():
    result = result_for(LineString([(X, Y, 0), (X + 3, Y + 4, 100)]))
    assert result.length_m == pytest.approx(5)
    assert result.geometry["coordinates"][1][2] == 100
    assert any("Altitude" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    ("geometry", "status"),
    [
        (None, "NULL_GEOMETRY"),
        (Polygon(), "EMPTY_GEOMETRY"),
        (LineString(), "EMPTY_GEOMETRY"),
        (GeometryCollection(), "EMPTY_GEOMETRY"),
        (Point(X, Y), "NO_MEASUREMENT"),
        (MultiPoint([(X, Y), (X + 1, Y + 1)]), "NO_MEASUREMENT"),
        (
            GeometryCollection([Point(X, Y), LineString([(X, Y), (X + 1, Y + 1)])]),
            "UNSUPPORTED_GEOMETRY",
        ),
        (
            Polygon([(X, Y), (X + 2, Y + 2), (X, Y + 2), (X + 2, Y), (X, Y)]),
            "INVALID_GEOMETRY",
        ),
    ],
)
def test_non_measurable_feature_statuses_are_explicit(geometry, status):
    result = result_for(geometry)
    assert result.status == status
    assert result.reason
    assert result.area_m2 is None
    assert result.length_m is None
    assert result.measurement_crs is None


@pytest.mark.parametrize(
    "coordinates",
    [
        [(179.9, 10), (-179.9, 10)],
        [(0, 0), (2, 0)],
        [(0, 0), (0, 2)],
        [(10, 84.1), (10.01, 84.2)],
        [(10, -80.1), (10.01, -80.2)],
    ],
)
def test_outside_policy_geometries_are_retained_without_false_measurement(coordinates):
    result = result_for(LineString(coordinates), WGS84)
    assert result.status == "OUTSIDE_SUPPORTED_EXTENT"
    assert result.geometry is not None
    assert result.area_m2 is None and result.length_m is None


@pytest.mark.parametrize("coordinates", [[(181, 10), (181.01, 10)], [(10, 91), (10.01, 91)]])
def test_out_of_range_wgs84_coordinates_are_invalid(coordinates):
    result = result_for(LineString(coordinates), WGS84)
    assert result.status == "INVALID_GEOMETRY"
    assert result.length_m is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_geometry_is_not_serialized(value):
    # Shapely versions may warn while constructing intentionally invalid input.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        geometry = LineString([(X, Y), (value, Y + 1)])
    result = result_for(geometry)
    assert result.status == "INVALID_GEOMETRY"
    assert result.geometry is None
    assert "NaN" not in result.model_dump_json()


def test_finite_json_recurses_into_coordinates_and_properties():
    assert finite_json({"coordinates": [[1, 2], [3.4, 5]], "name": "field", "empty": None})
    assert not finite_json({"nested": [1, {"x": float("nan")}]})
    assert not finite_json((1, float("inf")))


def test_web_mercator_is_reprojected_instead_of_treated_as_measurement_space():
    from pyproj import Transformer
    from shapely import transform

    geographic = box(10, 60, 10.001, 60.001)
    mercator = transform(
        geographic, Transformer.from_crs(4326, 3857, always_xy=True).transform, interleaved=False
    )
    expected = abs(GEOD.geometry_area_perimeter(geographic)[0])
    result = result_for(mercator, CRS.from_epsg(3857))
    assert result.status == "MEASURED"
    assert result.area_m2 == pytest.approx(expected, rel=0.004)
    assert result.area_m2 < mercator.area / 3
