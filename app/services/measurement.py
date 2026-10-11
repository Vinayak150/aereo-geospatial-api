"""Bounded, per-feature WGS84 UTM measurements; no silent geometry repairs."""

import math
from typing import Any

import numpy as np
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely import get_coordinates, transform
from shapely.errors import GEOSException
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from app.schemas import FeatureResult

WGS84 = CRS.from_epsg(4326)


def finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_json(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_json(item) for item in value)
    return True


def measure(
    geometry: BaseGeometry | None,
    source: CRS,
    feature_id: str,
    index: int,
    properties: dict[str, Any],
) -> FeatureResult:
    result = FeatureResult(
        feature_id=feature_id,
        index=index,
        geometry_type=None,
        geometry=None,
        properties=properties,
        crs=source.to_string(),
        status="NULL_GEOMETRY",
        reason="Feature has no geometry.",
    )
    if geometry is None:
        return result
    result.geometry_type = geometry.geom_type
    if geometry.is_empty:
        result.status, result.reason = "EMPTY_GEOMETRY", "Feature geometry is empty."
        return result
    representation = mapping(geometry)
    if not finite_json(representation):
        result.status, result.reason = "INVALID_GEOMETRY", "Coordinates must be finite."
        return result
    result.geometry = representation
    if not geometry.is_valid:
        result.status, result.reason = "INVALID_GEOMETRY", explain_validity(geometry)
        return result
    if geometry.has_z:
        result.warnings.append("Altitude is preserved but ignored for 2D measurements.")
    try:
        # Validate angles in the source CRS before PROJ can normalize/wrap them.
        # Geographic axes may use degrees or grads rather than radians.
        if source.is_geographic:
            longitude_axis = next(
                axis for axis in source.axis_info if axis.direction in {"east", "west"}
            )
            latitude_axis = next(
                axis for axis in source.axis_info if axis.direction in {"north", "south"}
            )
            original = get_coordinates(geometry)
            if np.any(
                np.abs(original[:, 0]) * longitude_axis.unit_conversion_factor > math.pi + 1e-12
            ) or np.any(
                np.abs(original[:, 1]) * latitude_axis.unit_conversion_factor > math.pi / 2 + 1e-12
            ):
                result.status, result.reason = "INVALID_GEOMETRY", "Invalid geographic coordinates."
                return result
        geographic = transform(
            geometry,
            Transformer.from_crs(
                source, WGS84, always_xy=True, allow_ballpark=False, only_best=True
            ).transform,
            interleaved=False,
        )
        coordinates = get_coordinates(geographic)
        if (
            not np.isfinite(coordinates).all()
            or np.any(np.abs(coordinates[:, 0]) > 180)
            or np.any(np.abs(coordinates[:, 1]) > 90)
        ):
            result.status = "INVALID_GEOMETRY"
            result.reason = "Coordinates cannot be represented as valid longitude/latitude."
            return result
        if geometry.geom_type in {"Point", "MultiPoint"}:
            result.status, result.reason = "NO_MEASUREMENT", "Points have no area or length."
            return result
        if geometry.geom_type not in {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}:
            result.status = "UNSUPPORTED_GEOMETRY"
            result.reason = "Mixed geometry collections are preserved but not measured."
            return result
        west, south, east, north = geographic.bounds
        if east - west > 1 or north - south > 1 or south < -80 or north > 84:
            result.status = "OUTSIDE_SUPPORTED_EXTENT"
            result.reason = (
                "Local UTM policy requires a feature extent <= 1 degree on each axis "
                "and latitude between 80S and 84N; antimeridian crossings are unsupported."
            )
            return result
        zone = min(60, max(1, int(((west + east) / 2 + 180) // 6) + 1))
        epsg = (32600 if (south + north) / 2 >= 0 else 32700) + zone
        target = CRS.from_epsg(epsg)
        projected = transform(
            geometry,
            Transformer.from_crs(
                source, target, always_xy=True, allow_ballpark=False, only_best=True
            ).transform,
            interleaved=False,
        )
        value = projected.area if "Polygon" in geometry.geom_type else projected.length
        if not math.isfinite(value) or not projected.is_valid:
            raise ValueError("Invalid projected geometry")
        result.status, result.reason = "MEASURED", None
        result.measurement_crs = target.to_string()
        result.method = "planar_local_utm"
        if "Polygon" in geometry.geom_type:
            result.area_m2 = value
        else:
            result.length_m = value
        return result
    except (ProjError, GEOSException, ValueError, OverflowError, StopIteration):
        result.status = "TRANSFORMATION_FAILED"
        result.reason = "A reliable coordinate transformation is unavailable."
        return result
