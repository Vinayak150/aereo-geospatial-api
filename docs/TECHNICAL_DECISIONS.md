# Technical decisions

This is a bounded local API submission. Its engineering choices make measurement assumptions inspectable; they do not establish that an unauthenticated process is safe to expose to the public internet.

## FastAPI and a small service boundary

FastAPI supplies multipart upload handling, typed request validation, response schemas, and generated OpenAPI documentation. Pydantic models define the public response contract. The HTTP layer in `app/main.py` coordinates requests; `services/files.py` coordinates ingestion; `services/parsing.py` and `services/archive.py` read and validate files; `services/measurement.py` contains measurement policy; `db.py` stores completed results.

Parsing and measurement run in FastAPI's thread pool so this blocking work does not execute directly on the event loop. This does not make CPU work unlimited or turn ingestion into a durable background job. Requests remain synchronous from the client's perspective. Celery and Redis would add operational dependencies without resolving an assignment requirement.

## Reading the formats

KML input must have the KML 2.2 root namespace. `defusedxml` rejects DTDs and entity declarations before the document reaches FastKML. Structural limits, explicit ring closure and geometry-child cardinality are checked, and NetworkLink, Model, Track, and MultiTrack content is rejected. FastKML interprets supported placemarks and Shapely represents their geometries. Nested Document and Folder containers are traversed. Placemark IDs are preserved where supplied; otherwise a stable ordinal within that upload is used. Name, description, address, and ExtendedData are retained when present. KML coordinates are interpreted as WGS84 longitude/latitude, with altitude retained but excluded from measurements.

Shapefiles are read through Pyogrio/GDAL after ZIP validation. An archive must contain exactly one `.shp` and matching `.shx`, `.dbf`, and `.prj` files. `.cpg` is used when available. Names are matched case-insensitively, including an ordinary enclosing directory. Multiple datasets are rejected rather than selected arbitrarily. Requiring `.prj` is this implementation's explicit policy: guessing a CRS can produce plausible but incorrect numbers. Format signature and GDAL driver checks supplement extension checks. GDAL feature IDs and DBF attributes are preserved.

The stored geometry is a GeoJSON-shaped geometry object in the **source CRS**. It is not a claim of RFC 7946 GeoJSON compliance for projected data. Consumers must read the associated `crs` before interpreting coordinates. Files are not converted into a separate downloadable GeoJSON format.

## Geographic coordinates are not metre coordinates

A geographic CRS describes positions using angular coordinates relative to a datum. EPSG:4326 uses WGS84 angular coordinates. One degree of longitude covers different distances at different latitudes; applying Cartesian area or length to longitude/latitude therefore produces square degrees or degrees, not square metres or metres.

A projected CRS maps positions onto a plane with linear units, introducing projection distortion. A projected CRS can use feet rather than metres, and a familiar projection such as Web Mercator is not automatically appropriate for measurement. The service consequently evaluates every feature in WGS84 and transforms every measurable feature into its selected metric CRS, including features already supplied in a projected CRS.

`Transformer.from_crs(..., always_xy=True)` fixes the application convention to x/y: longitude/latitude for geographic input. This avoids confusing authority axis order with the coordinate order used by the file readers. Ballpark transformations are disabled and the best transformation is requested. PROJ network access is disabled at startup. A missing required transformation resource produces a feature failure rather than a guessed result.

## The bounded UTM policy

Each valid polygon or line is considered independently:

1. Transform it to WGS84 to inspect its extent.
2. Require longitude and latitude spans of at most one degree each, and latitude within 80°S to 84°N.
3. Select the ordinary six-degree UTM zone from the midpoint longitude of its WGS84 bounds; select the northern or southern WGS84 UTM CRS using the midpoint latitude.
4. Transform the original geometry into that CRS and compute Shapely's planar area or length.
5. Return `measurement_crs`, `method: planar_local_utm`, and either `area_m2` or `length_m`.

The selection uses ordinary UTM zones rather than a full geographic zoning rules engine. Features near a zone boundary may extend slightly into the adjacent zone. Each feature still uses one continuous projection; components of a multipart feature are measured together. Separate features in the same upload may have different measurement CRSs.

Broad extents, polar regions, and antimeridian-crossing features are outside this policy and receive `OUTSIDE_SUPPORTED_EXTENT`. Geometry and attributes remain available; measurement fields stay null. This deliberate coverage limit is not a global measurement solution. UTM is conformal, not equal-area, and its scale factor differs from one. Even accepted results are planar approximations, not exact ellipsoidal or survey-ground measurements. Z/altitude is ignored for calculation, so line length is not terrain-following distance and area is not sloped surface area.

The test design compares geographic examples against independent PyProj `Geod` ellipsoid calculations, with 0.2% relative tolerance for length and 0.4% for area. These are conservative comparison tolerances for the selected local examples and their projection distortion, not a global accuracy guarantee. Analytically known metric rectangles and 3–4–5 lines test the arithmetic much more tightly. The test report records whether the suite actually ran successfully.

An equal-area projection would be preferable for extensive area accounting; ellipsoidal geodesic calculations would suit another class of distance queries. Supporting those requires explicit semantics for edges, antimeridian handling, and validation. They are future policies rather than undocumented fallbacks.

## Holes, multipart data, and invalid features

Shapely polygon area subtracts interior rings from the exterior ring. MultiPolygon area sums constituent polygon areas; MultiLineString length sums its lines. LineString receives length only, and Polygon receives area only. Point and MultiPoint receive `NO_MEASUREMENT`, not a misleading measurement of zero. Mixed GeometryCollection objects are preserved with `UNSUPPORTED_GEOMETRY`.

Null, empty, invalid, nonfinite, and untransformable geometries have explicit feature statuses. The service does not silently apply `buffer(0)` or `make_valid`: repairing a self-crossing boundary can change the intended area or split a feature. Nonfinite geometry coordinates are not emitted as invalid JSON. A parseable file can finish with skipped features; `COMPLETED` means ingestion finished, not that every feature has a valid measurement. Clients should inspect `measured_count`, `skipped_count`, and individual statuses.

## Upload defenses and their limits

The request body is bounded before multipart parsing, including requests that omit a Content-Length. The application separately bounds file bytes. ZIP handling checks every member for traversal, absolute paths, unsafe file types, symlinks, duplicate case-insensitive paths, encryption, and nested archives. It limits entry count, declared expansion, compression ratio, and actual decompressed bytes. Every file member is read to check corruption/CRC, including ignored sidecars. Selected files are written under generated names in an isolated temporary directory; the supplied filename is metadata, never a filesystem destination.

KML has entity defenses, depth and element limits, a placemark limit, and unsupported remote-reference checks. Parsed datasets have feature and coordinate-count limits. These are practical bounds, not complete resource isolation: XML trees and native GIS parsers can allocate memory before all semantic limits are checked. GDAL, GEOS, PROJ, and XML parser vulnerabilities remain dependency risks. Concurrent requests can multiply per-request memory use. The documented Uvicorn command caps concurrent connections at eight, and Compose adds container CPU/memory limits. There is no per-job processing time budget, per-user quota, authenticated ownership, or sandboxed worker process.

Run this submission on a trusted local machine or isolated evaluation environment. Before public service, add authentication and authorization, upload rate and concurrency limits, a constrained worker process with time/memory budgets, dependency patching, retention rules, observability, and a reverse proxy configured for request limits. These are deployment work, not claims about the current implementation.

## Consistent errors and atomic persistence

Malformed requests, unsupported content, resource-limit violations, and missing IDs have structured `error.code` and `error.message` responses. Request validation errors do not echo uploaded bytes or raw validation internals. Unexpected failures return a generic error to the client and log details server-side; logs should be handled as potentially sensitive operational data.

SQLite via SQLAlchemy keeps setup portable. File metadata and per-feature result JSON are stored in separate tables. A file ID plus a feature index identifies each persisted row even when a source file reuses feature IDs. Upload IDs are random UUIDs. SHA-256 is recorded for identification, but repeated content intentionally creates a new upload rather than deduplicating data.

Parsing and measurement finish before a single transaction inserts metadata and all features. A failed insert rolls back the entire transaction. Successful reads reuse stored results; they do not repeatedly invoke GIS parsers. Result pages have stable source order and bounded page size. Persistence across restarts depends on retaining the configured database file or Docker volume.

Raw uploads and extracted temporary files are discarded after ingestion. Original geometry, attributes, and computed results are deliberately persisted because the retrieval API needs them. This avoids storing a second raw copy, but still consumes disk and may retain sensitive user data. There is no delete endpoint or retention scheduler. SQLite WAL mode and a busy timeout support modest local concurrency; there is no benchmark or multi-node scaling claim. Schema creation is suitable for a fresh submission, not a production migration system.

## Alternatives and future scope

GeoPandas would be useful for dataframe analysis, but Pyogrio, Shapely, and PyProj cover this service's direct feature-processing path without an additional dataframe layer. PostgreSQL/PostGIS would become useful for spatial queries and shared deployment; neither is needed to retrieve results by upload ID. Background queues would be appropriate if bounded synchronous uploads cease to fit workload needs. A future global policy should add antimeridian-aware geometry handling and explicitly chosen geodesic/equal-area measurement semantics before expanding geographic coverage.

Other improvements include storage retention, migrations, isolated parsing workers, richer KML metadata fidelity, wider datum/grid support, and measured performance testing. These should follow demonstrated need and independent correctness tests.

## Evidence and the decisions it supports

[Executed evidence](MEASUREMENT_EVIDENCE.md) separates analytic agreement from projected/geodesic model differences. The 16 cases include exact local geometry, holes, multipart shapes, US survey feet, southern-hemisphere data, zone boundaries, a one-degree extent and explicit exclusions. The report records a difference rather than treating the ellipsoidal result as an identical planar ground truth. The largest observed area model difference in those cases is about 0.19631220%; that is evidence about those fixtures, not a global accuracy claim.

The five Hypothesis properties call the real application. Area additivity is checked only when components and aggregate select the same projected CRS; independently selected CRSs would invalidate that premise. Reversal preserves vertices and bounding boxes. Ordering is tested across actual HTTP uploads, comparing source IDs and measurements rather than upload UUIDs or positional indices. Runs are deterministic under the pinned library, with 40 accepted examples per property and no timing deadline; this avoids machine-speed-dependent failures without suppressing numerical failures.

| Decision | Why it fits here | What would justify a change |
|---|---|---|
| Local UTM rather than geodesic-only output | Meets the brief's projected-measurement requirement, supplies metres and a visible CRS for area and length | A separate global/geodesic contract with explicit edge semantics; equal-area projections for area accounting |
| Bounded geographic coverage | Refusing unsuitable measurements is defensible; the evidence suite exposes approximation near the limits | Independent validation of a broader policy, not merely widening thresholds |
| SQLite rather than PostgreSQL/PostGIS | Retrieval is by file ID; no shared service or spatial query is required | Shared multi-user deployment or actual spatial indexing/query needs |
| Synchronous ingestion rather than a queue | Bounded input and one atomic transaction are easy to reproduce and explain | Measured processing latency requiring durable jobs, cancellation and retries |
| Fixed input limits rather than scale claims | Limits are enforceable acceptance rules, tested at the boundary | Workload measurements and isolated-worker memory/time budgets; limits alone do not prove worst-case resource safety |
| Reject structural ambiguity rather than repair | The review reproduced FastKML silently retaining only the first repeated boundary/coordinate block | An explicit repair workflow with provenance and user intent, not an implicit parser fallback |
| Small internship-assignment scope | A candidate can trace an upload, explain one projection policy and defend a transaction | Product requirements beyond the brief; unrelated infrastructure would obscure those skills |

The evidence script's saved-number check has a small floating-point reproduction allowance separate from its model-comparison criteria. Derived differences inherit operand allowances so subtractive cancellation does not create platform-dependent false failures. No runtime projection or API schema changed during the differentiation pass.

## Primary references consulted

- [PyProj Transformer](https://pyproj4.github.io/pyproj/stable/api/transformer.html): coordinate order and transformation controls.
- [PROJ UTM](https://proj.org/en/stable/operations/projections/utm.html): projection definition and zone parameters.
- [Pyogrio API](https://pyogrio.readthedocs.io/en/latest/api.html): file metadata and feature reading.
- [OGC KML](https://www.ogc.org/standards/kml/): format standard.

Library signatures and installed implementations were also inspected locally; the pinned dependencies and executed tests are the evidence for this repository's actual behavior.
