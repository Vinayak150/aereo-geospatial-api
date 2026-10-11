import io
import zipfile
from pathlib import Path

import numpy as np
import pyogrio.raw
import pytest
from fastapi.testclient import TestClient
from shapely import to_wkb
from shapely.geometry import Polygon

from app.config import Settings
from app.main import create_app


def kml_bytes(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + body + "</Document></kml>"
    ).encode()


def zip_bytes(entries: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def config(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db")


@pytest.fixture
def client(config):
    with TestClient(create_app(config)) as api:
        yield api


@pytest.fixture
def kml():
    return kml_bytes("""
      <Folder><Placemark id="parcel-1"><name>Mine parcel</name>
      <ExtendedData><Data name="owner"><value>Aereo</value></Data>
      <SchemaData schemaUrl="#s"><SimpleData name="code">42</SimpleData></SchemaData></ExtendedData>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
      77,13 77.001,13 77.001,13.001 77,13.001 77,13
      </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Folder>
      <Placemark id="road"><LineString><coordinates>77,13 77.001,13</coordinates></LineString></Placemark>
      <Placemark id="marker"><Point><coordinates>77,13,25</coordinates></Point></Placemark>
      <Placemark id="null"><name>No geometry</name></Placemark>
    """)


@pytest.fixture
def shape_entries(tmp_path: Path):
    directory = tmp_path / "source"
    directory.mkdir()
    polygon = Polygon(
        [
            (500000, 1400000),
            (500010, 1400000),
            (500010, 1400020),
            (500000, 1400020),
            (500000, 1400000),
        ]
    )
    pyogrio.raw.write(
        directory / "survey.shp",
        to_wkb(np.array([polygon], dtype=object)),
        [np.array(["mine"], dtype=object), np.array([7])],
        ["site", "number"],
        driver="ESRI Shapefile",
        geometry_type="Polygon",
        crs="EPSG:32643",
    )
    return {f"nested/{item.name}": item.read_bytes() for item in directory.iterdir()}


@pytest.fixture
def shape_zip(shape_entries):
    return zip_bytes(shape_entries)
