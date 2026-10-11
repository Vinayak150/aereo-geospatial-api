"""Generate small, genuine GIS files with independently known projected dimensions."""

import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pyogrio.raw
from shapely import to_wkb
from shapely.geometry import box

DESTINATION = Path(__file__).resolve().parents[1] / "sample_data"


def main() -> None:
    DESTINATION.mkdir(exist_ok=True)
    (DESTINATION / "bengaluru.kml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Example survey</name>
  <Placemark id="parcel"><name>Example parcel</name>
    <ExtendedData><Data name="purpose"><value>Assignment demonstration</value></Data></ExtendedData>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      77.59,12.97 77.591,12.97 77.591,12.971 77.59,12.971 77.59,12.97
    </coordinates></LinearRing></outerBoundaryIs></Polygon>
  </Placemark>
  <Placemark id="road"><name>Example road</name><LineString><coordinates>
    77.59,12.97 77.591,12.971
  </coordinates></LineString></Placemark>
  <Placemark id="marker"><name>Survey marker</name><Point><coordinates>
    77.59,12.97,900
  </coordinates></Point></Placemark>
</Document></kml>
""",
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pyogrio.raw.write(
            root / "reference.shp",
            to_wkb(np.array([box(500000, 1400000, 500010, 1400020)], dtype=object)),
            [np.array(["10m x 20m"], dtype=object), np.array([200.0])],
            ["name", "area_m2"],
            driver="ESRI Shapefile",
            geometry_type="Polygon",
            crs="EPSG:32643",
        )
        with zipfile.ZipFile(
            DESTINATION / "reference_rectangle.zip", "w", zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(root.iterdir()):
                entry = zipfile.ZipInfo("survey/" + path.name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())


if __name__ == "__main__":
    main()
