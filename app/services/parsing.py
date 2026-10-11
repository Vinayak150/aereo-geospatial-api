"""Established KML and GDAL readers behind resource and content validation."""

import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from xml.etree import ElementTree

import numpy as np
import pyogrio
from defusedxml import ElementTree as SafeXML
from defusedxml.common import DefusedXmlException
from fastkml import KML, Placemark
from fastkml.data import Data, SchemaData
from fastkml.exceptions import FastKMLError
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely import from_wkb, get_num_coordinates
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.config import Settings
from app.errors import APIError
from app.services.archive import extract_shapefile


@dataclass
class SourceFeature:
    feature_id: str
    geometry: BaseGeometry | None
    properties: dict[str, Any]


@dataclass
class Dataset:
    crs: CRS
    features: list[SourceFeature]


def json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def read_kml(content: bytes, settings: Settings) -> Dataset:
    try:
        root = SafeXML.fromstring(
            content, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
        if root.tag != "{http://www.opengis.net/kml/2.2}kml":
            raise APIError("INVALID_KML", "Expected a KML 2.2 root element and namespace.")
        stack = [(root, 1)]
        elements = 0
        placemarks = 0
        coordinates = 0
        while stack:
            element, depth = stack.pop()
            elements += 1
            if depth > settings.max_xml_depth or elements > settings.max_xml_elements:
                raise APIError("KML_LIMIT", "KML structure exceeds configured limits.", 413)
            local_name = element.tag.rsplit("}", 1)[-1]
            # FastKML can select the first child when malformed XML repeats a
            # singleton. Reject ambiguity before any boundary/coordinates vanish.
            namespace = "{http://www.opengis.net/kml/2.2}"
            required_child = {
                "Point": "coordinates",
                "LineString": "coordinates",
                "LinearRing": "coordinates",
                "Polygon": "outerBoundaryIs",
                "outerBoundaryIs": "LinearRing",
                "innerBoundaryIs": "LinearRing",
            }.get(local_name)
            if required_child and len(element.findall(namespace + required_child)) != 1:
                raise APIError(
                    "INVALID_KML", f"{local_name} requires exactly one {required_child} child."
                )
            if local_name == "NetworkLink":
                raise APIError("UNSUPPORTED_KML", "NetworkLink references are not supported.")
            if local_name in {"Track", "MultiTrack", "Model"}:
                raise APIError("UNSUPPORTED_KML", "KML models and tracks are not supported.")
            if local_name == "LinearRing":
                rings = [
                    child for child in element if child.tag.rsplit("}", 1)[-1] == "coordinates"
                ]
                tuples = (rings[0].text or "").split() if len(rings) == 1 else []
                if len(tuples) < 4 or tuple(map(float, tuples[0].split(","))) != tuple(
                    map(float, tuples[-1].split(","))
                ):
                    raise APIError(
                        "INVALID_KML",
                        "LinearRing must contain at least four coordinates and be explicitly closed.",
                    )
            if local_name == "Placemark":
                geometry_children = [
                    child
                    for child in element
                    if child.tag.rsplit("}", 1)[-1]
                    in {"Point", "LineString", "LinearRing", "Polygon", "MultiGeometry"}
                ]
                if len(geometry_children) > 1:
                    raise APIError(
                        "INVALID_KML", "Multiple geometries must be wrapped in MultiGeometry."
                    )
                placemarks += 1
                if placemarks > settings.max_features:
                    raise APIError("FEATURE_LIMIT", "File contains too many features.", 413)
            if local_name == "coordinates":
                coordinates += len((element.text or "").split(None, settings.max_coordinates))
                if coordinates > settings.max_coordinates:
                    raise APIError(
                        "GEOMETRY_LIMIT", "File contains too many geometry coordinates.", 413
                    )
            stack.extend((child, depth + 1) for child in element)
        document = KML.from_string(ElementTree.tostring(root, encoding="unicode"), strict=True)
        features: list[SourceFeature] = []

        def visit(container: Any) -> None:
            for item in container.features:
                if isinstance(item, Placemark):
                    properties: dict[str, Any] = {}
                    for field in ("name", "description", "address"):
                        if getattr(item, field, None) is not None:
                            properties[field] = str(getattr(item, field))
                    extended: dict[str, Any] = {}
                    if item.extended_data:
                        for entry in item.extended_data.elements:
                            if isinstance(entry, Data):
                                extended[str(entry.name)] = entry.value
                            elif isinstance(entry, SchemaData):
                                for data in entry.data:
                                    extended[str(data.name)] = data.value
                    if extended:
                        properties["extended_data"] = extended
                    features.append(
                        SourceFeature(
                            str(item.id) if item.id else str(len(features)),
                            shape(item.geometry) if item.geometry is not None else None,
                            properties,
                        )
                    )
                elif hasattr(item, "features"):
                    visit(item)

        visit(document)
        return Dataset(CRS.from_epsg(4326), features)
    except APIError:
        raise
    except (
        DefusedXmlException,
        ElementTree.ParseError,
        FastKMLError,
        GEOSException,
        ValueError,
        TypeError,
        AttributeError,
        IndexError,
        KeyError,
        OverflowError,
    ) as exc:
        raise APIError(
            "INVALID_KML", "KML is malformed or contains invalid geometry data."
        ) from exc


def read_shapefile(content: bytes, settings: Settings) -> Dataset:
    with TemporaryDirectory(prefix="aereo-") as temporary:
        path = extract_shapefile(content, Path(temporary), settings)
        try:
            # A .shp extension alone is insufficient: verify the fixed format signature.
            with path.open("rb") as stream:
                if stream.read(4) != b"\x00\x00\x27\x0a":
                    raise APIError("INVALID_SHAPEFILE", "Invalid Shapefile signature.")
            info = pyogrio.read_info(path)
            if info["driver"] != "ESRI Shapefile":
                raise APIError("INVALID_SHAPEFILE", "Expected an ESRI Shapefile dataset.")
            if not info["crs"]:
                raise APIError(
                    "MISSING_CRS", "Shapefile must contain a valid .prj coordinate system."
                )
            crs = CRS.from_user_input(info["crs"])
            if not (crs.is_projected or crs.is_geographic) or crs.is_compound:
                raise APIError(
                    "UNSUPPORTED_CRS", "Only geographic or projected horizontal CRS is supported."
                )
            if info["features"] > settings.max_features:
                raise APIError("FEATURE_LIMIT", "File contains too many features.", 413)
            meta, identifiers, geometries, columns = pyogrio.raw.read(
                path,
                return_fids=True,
                max_features=settings.max_features + 1,
                datetime_as_string=True,
            )
            if len(identifiers) > settings.max_features:
                raise APIError("FEATURE_LIMIT", "File contains too many features.", 413)
            features = []
            for index, identifier in enumerate(identifiers):
                properties = {
                    str(name): json_value(column[index])
                    for name, column in zip(meta["fields"], columns, strict=True)
                }
                features.append(
                    SourceFeature(str(identifier), from_wkb(geometries[index]), properties)
                )
            return Dataset(crs, features)
        except APIError:
            raise
        except CRSError as exc:
            raise APIError(
                "INVALID_CRS", "Shapefile coordinate system cannot be interpreted."
            ) from exc
        except (
            pyogrio.errors.DataSourceError,
            pyogrio.errors.DataLayerError,
            pyogrio.errors.FeatureError,
            pyogrio.errors.GeometryError,
            GEOSException,
            ValueError,
            OSError,
            IndexError,
        ) as exc:
            raise APIError("INVALID_SHAPEFILE", "Shapefile data could not be read.") from exc


def parse_file(content: bytes, file_format: str, settings: Settings) -> Dataset:
    dataset = (
        read_kml(content, settings) if file_format == "kml" else read_shapefile(content, settings)
    )
    if not dataset.features:
        raise APIError("EMPTY_DATASET", "File does not contain any features.")
    count = sum(int(get_num_coordinates(item.geometry)) for item in dataset.features)
    if count > settings.max_coordinates:
        raise APIError("GEOMETRY_LIMIT", "File contains too many geometry coordinates.", 413)
    return dataset
