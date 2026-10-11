from pathlib import Path

import pytest

from tests.test_api import post

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.mark.parametrize("name,count", [("bengaluru.kml", 3), ("reference_rectangle.zip", 1)])
def test_bundled_real_files(client, name, count):
    response = post(client, (SAMPLES / name).read_bytes(), name)
    assert response.status_code == 201, response.text
    assert response.json()["feature_count"] == count
    data = client.get(f"/api/files/{response.json()['id']}/measurements/").json()
    if name.endswith(".zip"):
        assert data["features"][0]["area_m2"] == pytest.approx(200, abs=1e-6)


def test_unclosed_kml_ring_is_not_silently_repaired(client):
    from tests.conftest import kml_bytes

    content = kml_bytes("""<Placemark><Polygon><outerBoundaryIs><LinearRing>
    <coordinates>77,13 77.001,13 77.001,13.001 77,13.001</coordinates>
    </LinearRing></outerBoundaryIs></Polygon></Placemark>""")
    response = post(client, content)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_KML"


@pytest.mark.parametrize("epsg,longitude", [(4269, 181), (4807, 201)])
def test_other_geographic_crs_angles_are_validated_before_wrapping(epsg, longitude):
    from pyproj import CRS
    from shapely.geometry import Point

    from app.services.measurement import measure

    result = measure(Point(longitude, 10), CRS.from_epsg(epsg), "bad", 0, {})
    assert result.status == "INVALID_GEOMETRY"
    assert result.area_m2 is None and result.length_m is None
