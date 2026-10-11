"""Execute the real measurement service against independent numeric references."""

import argparse
import json
import math
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from pyproj import CRS, Geod, network
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping
from shapely.geometry.base import BaseGeometry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.measurement import measure  # noqa: E402

GEOD = Geod(ellps="WGS84")
X, Y = 500000, 1400000


@dataclass(frozen=True)
class Case:
    name: str
    location: str
    source: CRS
    geometry: BaseGeometry
    field: str
    reference: float | None
    reference_method: str
    expected_crs: str | None
    relative_tolerance: float = 0
    absolute_tolerance: float = 1e-6
    expected_status: str = "MEASURED"


def fixtures() -> list[Case]:
    metric, wgs = CRS.from_epsg(32643), CRS.from_epsg(4326)
    cases = [
        Case(
            "rectangle",
            "UTM 43N: E500000 N1400000",
            metric,
            box(X, Y, X + 10, Y + 20),
            "area_m2",
            10 * 20,
            "Analytic: 10 × 20",
            "EPSG:32643",
        ),
        Case(
            "hole",
            "Same UTM site",
            metric,
            Polygon(
                box(X, Y, X + 10, Y + 20).exterior.coords,
                [box(X + 2, Y + 2, X + 4, Y + 7).exterior.coords],
            ),
            "area_m2",
            10 * 20 - 2 * 5,
            "Analytic: 200 − 10",
            "EPSG:32643",
        ),
        Case(
            "multipart",
            "Same UTM site; disjoint squares",
            metric,
            MultiPolygon([box(X, Y, X + 10, Y + 10), box(X + 20, Y, X + 25, Y + 5)]),
            "area_m2",
            10**2 + 5**2,
            "Analytic: 100 + 25",
            "EPSG:32643",
        ),
        Case(
            "line_3_4_5",
            "Same UTM site",
            metric,
            LineString([(X, Y), (X + 3, Y + 4)]),
            "length_m",
            math.hypot(3, 4),
            "Analytic: √(3² + 4²)",
            "EPSG:32643",
            absolute_tolerance=1e-8,
        ),
    ]
    conversion = 1200 / 3937  # Internationally defined US survey foot, independently applied.
    feet = CRS.from_proj4("+proj=utm +zone=43 +datum=WGS84 +units=us-ft +no_defs")
    cases.append(
        Case(
            "survey_feet",
            "Same UTM site; coordinates in US survey feet",
            feet,
            box(X / conversion, Y / conversion, (X + 10) / conversion, (Y + 20) / conversion),
            "area_m2",
            200,
            "Analytic: 10 m × 20 m; 1 ftUS = 1200/3937 m",
            "EPSG:32643",
        )
    )
    geographic = [
        ("bengaluru_area", "Bengaluru 77.6E 12.9N", box(77.6, 12.9, 77.61, 12.91), "EPSG:32643"),
        ("bengaluru_line", "Bengaluru", LineString([(77.6, 12.9), (77.602, 12.903)]), "EPSG:32643"),
        ("south_area", "Cape Town 18.4E 33.9S", box(18.4, -33.9, 18.41, -33.89), "EPSG:32734"),
        ("south_line", "Cape Town", LineString([(18.4, -33.9), (18.402, -33.897)]), "EPSG:32734"),
        (
            "zone_boundary",
            "Equator; crosses 6E zone boundary",
            box(5.995, 0, 6.005, 0.01),
            "EPSG:32632",
        ),
        (
            "near_extent_area",
            "Equator; 0.9999° wide, reaches 3.4999° from zone meridian",
            box(5.5, 0, 6.4999, 0.9999),
            "EPSG:32631",
        ),
        (
            "exact_extent_line",
            "Equator; exactly 1° wide",
            LineString([(5.499, 0), (6.499, 0)]),
            "EPSG:32631",
        ),
        ("north_limit", "10E, upper latitude 84N", box(10, 83.99, 10.01, 84), "EPSG:32632"),
    ]
    for name, location, geometry, target in geographic:
        area = geometry.geom_type == "Polygon"
        coordinates = geometry.exterior.coords if area else geometry.coords
        longitudes, latitudes = zip(*coordinates, strict=True)
        reference = (
            abs(GEOD.polygon_area_perimeter(longitudes, latitudes)[0])
            if area
            else GEOD.line_length(longitudes, latitudes)
        )
        cases.append(
            Case(
                name,
                location,
                wgs,
                geometry,
                "area_m2" if area else "length_m",
                reference,
                "WGS84 Geod; geodesic edges",
                target,
                relative_tolerance=0.004 if area else 0.002,
                absolute_tolerance=0,
            )
        )
    for name, location, geometry in [
        ("over_extent", "Equator; 1.0001° wide", LineString([(5.499, 0), (6.4991, 0)])),
        ("polar", "Above 84N", LineString([(10, 84.01), (10.01, 84.02)])),
        ("antimeridian", "179.9E to 179.9W", LineString([(179.9, 10), (-179.9, 10)])),
    ]:
        cases.append(
            Case(
                name,
                location,
                wgs,
                geometry,
                "length_m",
                None,
                "Policy rejection; no numeric comparison",
                None,
                expected_status="OUTSIDE_SUPPORTED_EXTENT",
            )
        )
    return cases


def evaluate() -> dict:
    network.set_network_enabled(False)
    rows = []
    for index, case in enumerate(fixtures()):
        result = measure(case.geometry, case.source, case.name, index, {})
        actual = getattr(result, case.field)
        difference = (
            abs(actual - case.reference)
            if actual is not None and case.reference is not None
            else None
        )
        relative = difference / abs(case.reference) if difference is not None else None
        allowed = max(case.absolute_tolerance, abs(case.reference or 0) * case.relative_tolerance)
        passed = (
            result.status == case.expected_status and result.measurement_crs == case.expected_crs
        )
        passed = passed and (
            difference <= allowed
            if difference is not None
            else actual is None and case.reference is None
        )
        rows.append(
            {
                "fixture": case.name,
                "location": case.location,
                "source_crs": case.source.to_string(),
                "geometry": mapping(case.geometry),
                "measurement_crs": result.measurement_crs,
                "quantity": case.field,
                "actual": actual,
                "reference": case.reference,
                "reference_method": case.reference_method,
                "absolute_difference": difference,
                "relative_difference": relative,
                "absolute_tolerance": case.absolute_tolerance,
                "relative_tolerance": case.relative_tolerance,
                "status": result.status,
                "passed": passed,
            }
        )
    return {"libraries": {name: version(name) for name in ("shapely", "pyproj")}, "cases": rows}


def render(evidence: dict) -> str:
    lines = [
        "# Executed measurement evidence",
        "",
        "Generated by `python scripts/measurement_evidence.py --write`; verify with `--check`.",
        "Exact fixture geometries, full-precision numbers and library versions are in [MEASUREMENT_EVIDENCE.json](MEASUREMENT_EVIDENCE.json).",
        "",
        "## Interpretation and acceptance criteria",
        "",
        "Analytic cases compare the same planar mathematical model. Their tolerances allow only floating-point roundoff: 1e-6 m² for area (including feet conversion) and 1e-8 m for the 3–4–5 line at UTM coordinate magnitudes near 1.4 million.",
        "Geod cases compare different models: straight segments between transformed vertices on a UTM plane versus shortest ellipsoidal geodesic edges on WGS84. The absolute/relative **differences are not absolute accuracy errors**. They include projection scale and edge-model differences. No edge densification is performed.",
        "The preselected fixture acceptance limits are 0.4% for area and 0.2% for length, consistent with the original tests. A local feature can extend to 3.5° from its chosen zone's central meridian; UTM scale distortion varies with position. These checks cover the listed fixtures, not all valid geometries, survey ground truth, terrain effects or a global error bound. Tolerances were selected before executing this suite.",
        "Geod is an independent ellipsoidal algorithm relative to the application's planar measurement path, but shares the PROJ ecosystem; this is not a separate vendor's surveying certification. Analytic fixtures provide references independent of PROJ's algorithms.",
        "",
        "## Results",
        "",
        "Numbers displayed to 12 significant digits. A dash means no measurement, never zero.",
        "",
        "| Fixture | Quantity | Actual | Reference | Absolute difference | Relative difference | Acceptance limit | Result |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in evidence["cases"]:

        def number(value):
            return "—" if value is None else f"{value:.12g}"

        tolerance = (
            f"{row['relative_tolerance']:.2%}"
            if row["relative_tolerance"]
            else f"{row['absolute_tolerance']:g} {'m²' if row['quantity'] == 'area_m2' else 'm'}"
        )
        if row["reference"] is None:
            tolerance = "Explicit policy rejection"
        lines.append(
            f"| {row['fixture']} | {row['quantity']} | {number(row['actual'])} | {number(row['reference'])} | {number(row['absolute_difference'])} | {'—' if row['relative_difference'] is None else format(row['relative_difference'], '.8%')} | {tolerance} | {'PASS' if row['passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "## Fixture locations and coordinate systems",
        "",
        "| Fixture | Location | Source CRS | Selected measurement CRS | Reference derivation |",
        "|---|---|---|---|---|",
    ]
    for row in evidence["cases"]:
        lines.append(
            f"| {row['fixture']} | {row['location']} | `{row['source_crs']}` | {row['measurement_crs'] or 'None'} | {row['reference_method']} |"
        )
    lines += [
        "",
        "## Reproduction guard",
        "",
        "`--check` recomputes every case, validates the acceptance criteria, checks fixture/status/CRS identity against the saved JSON, and checks that this Markdown is the rendering of that JSON. Saved measurements/references allow at most 1e-10 relative or 1e-8 absolute drift for cross-platform floating-point execution. Difference fields inherit the summed operand allowance (and reference normalization), avoiding a falsely strict cancellation check. This artifact-reproduction allowance is separate from the planar/geodesic model comparison tolerances.",
        "No endpoint, projection strategy or geographic coverage was expanded to make these comparisons pass.",
        "",
    ]
    return "\n".join(lines)


def check_snapshot(current: dict, saved: dict) -> None:
    if current["libraries"] != saved["libraries"]:
        raise ValueError(
            "Library versions differ; regenerate and review evidence after dependency changes."
        )
    for actual, previous in zip(current["cases"], saved["cases"], strict=True):
        for key in actual:
            left, right = actual[key], previous[key]
            if (
                key in {"actual", "reference", "absolute_difference", "relative_difference"}
                and left is not None
                and right is not None
            ):
                allowance = 1e-8
                operand_allowance = 2 * max(
                    1e-8, 1e-10 * max(abs(actual["actual"]), abs(actual["reference"]))
                )
                if key == "absolute_difference":
                    allowance = operand_allowance
                elif key == "relative_difference":
                    allowance = operand_allowance / abs(actual["reference"])
                if not math.isclose(left, right, rel_tol=1e-10, abs_tol=allowance):
                    raise ValueError(f"Evidence drift in {actual['fixture']}.{key}")
            elif json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                raise ValueError(f"Evidence changed in {actual['fixture']}.{key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    evidence = evaluate()
    failures = [row["fixture"] for row in evidence["cases"] if not row["passed"]]
    if failures:
        raise SystemExit(f"Measurement criteria failed: {failures}")
    data_file = ROOT / "docs/MEASUREMENT_EVIDENCE.json"
    markdown = ROOT / "docs/MEASUREMENT_EVIDENCE.md"
    if args.write:
        data_file.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
        markdown.write_text(render(evidence))
    else:
        saved = json.loads(data_file.read_text())
        check_snapshot(evidence, saved)
        if markdown.read_text() != render(saved):
            raise SystemExit("Markdown differs from recorded evidence; regenerate and review.")
    print(
        f"{len(evidence['cases'])} measurement/policy cases passed; evidence {'written' if args.write else 'verified'}."
    )


if __name__ == "__main__":
    main()
