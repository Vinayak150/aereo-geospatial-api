# Requirements traceability

The [official brief](https://ausindia-my.sharepoint.com/:w:/g/personal/gaurav_k_aereo_io/IQA-StSsm-LtRZ-g2y2_w7PpAQyEZxJY4tLIznWCOh9t2zs?e=50cxu9) is authoritative. [Normalized reading notes](OFFICIAL_ASSIGNMENT.md) record its four-page contents. The requirement column below uses short requirement labels/phrases from that reading, rather than treating the larger build prompt as the official assignment.

**Verification evidence:** On 2026-10-11, the full suite passed **111 tests**, with **95.28% statement coverage**. Ruff, formatting and mypy passed; real Uvicorn HTTP tests passed for both samples. See [delivery report](DELIVERY_REPORT.md) for commands and environmental limits. “Verified” means the named tests ran successfully; it does not imply global geographic coverage or public deployment readiness.

## Official minimum requirements

| ID | Official requirement phrase | Classification | Implementation | Responsible files | Relevant test/review target | Verification |
|---|---|---|---|---|---|---|
| O1 | “Django + Django REST Framework”; “FastAPI” | Mandatory choice of one | FastAPI application factory, typed schemas, generated OpenAPI | `app/main.py`, `app/schemas.py` | `tests/test_api.py::test_openapi_and_health` | Verified by full suite |
| O2 | “POST /api/files/”; “.zip”; “.kml” | Mandatory upload and formats; stated path implemented | Exactly one multipart field named `file`; parse supported KML or zipped Shapefile | `app/main.py`, `app/services/files.py`, `app/services/parsing.py`, `app/services/archive.py` | `tests/test_api.py::test_kml_contract`, `test_shapefile_real_roundtrip` | Verified by full suite |
| O3 | “Feature ID/index”; “Geometry type”; “Geometry”; “CRS”; “Properties/attributes” | Mandatory | Source identifiers, ordinal index, source geometry and CRS, and attributes in paginated feature results | `app/schemas.py`, `app/services/parsing.py`, `app/services/measurement.py` | `tests/test_measurement.py::test_original_geometry_and_feature_attributes_preserved`; `tests/test_api.py::test_kml_contract`, `test_shapefile_real_roundtrip` | Verified by full suite |
| O4 | Unsupported measurement geometry handled gracefully | Mandatory | Explicit feature statuses; no measurement for points or mixed collections; no silent repairs | `app/services/measurement.py`, `app/schemas.py` | `tests/test_measurement.py::test_non_measurable_feature_statuses_are_explicit` | Verified by full suite |
| O5 | “Polygon”; “Calculate Area” | Mandatory | Planar projected Polygon area, square metres | `app/services/measurement.py` | `tests/test_measurement.py::test_analytic_metric_area_including_holes_and_multipart`; `test_geographic_polygon_area_matches_independent_ellipsoid_reference` | Verified by full suite |
| O6 | “LineString”; “Calculate Length” | Mandatory | Planar projected LineString length, metres | `app/services/measurement.py` | `tests/test_measurement.py::test_analytic_metric_lengths`; `test_geographic_length_matches_independent_ellipsoid_reference` | Verified by full suite |
| O7 | “Point”; “No measurement required” | Mandatory | `NO_MEASUREMENT`, null area and length | `app/services/measurement.py` | `tests/test_measurement.py::test_non_measurable_feature_statuses_are_explicit` | Verified by full suite |
| O8 | “EPSG:4326”; projected coordinate system before calculating | Mandatory; selection strategy open | Reproject from source CRS into selected local WGS84 UTM; explicit bounds policy | `app/services/measurement.py` | `tests/test_measurement.py::test_geographic_length_matches_independent_ellipsoid_reference`; `test_geographic_polygon_area_matches_independent_ellipsoid_reference`; `test_projected_feet_are_converted_to_metres` | Verified by full suite |
| O9 | “GET /api/files/{id}/” | Mandatory | Retrieve persisted upload metadata; example keys retained, additional metadata included | `app/main.py`, `app/db.py`, `app/schemas.py` | `tests/test_api.py::test_kml_contract`, `test_pagination_and_unknown_ids`; `tests/test_review_regressions.py::test_metadata_is_identical_on_upload_and_subsequent_retrieval` | Verified by full suite |
| O10 | “GET /api/files/{id}/measurements/” | Mandatory | Retrieve source-ordered, paginated feature results and measurements | `app/main.py`, `app/db.py`, `app/schemas.py` | `tests/test_api.py::test_kml_contract`, `test_pagination_and_unknown_ids` | Verified by full suite |
| O11 | “README.md”; setup; API endpoints; example requests/responses | Mandatory documentation | Reproducible installation/start commands, endpoint guide, curl and response examples | `README.md` | Follow documented commands, inspect examples against live responses | Verified: native setup, API examples reviewed |
| O12 | Architecture; file-processing flow; measurement calculation flow; CRS handling | Mandatory documentation | Explain actual modules, synchronous pipeline, measurement policy and limits | `README.md`, `docs/TECHNICAL_DECISIONS.md` | Compare documentation with code and observed behavior | Reviewed against implementation |
| O13 | Design decisions and alternatives | Mandatory documentation | Explain framework, parsers, CRS, SQLite, transactions and rejected alternatives | `README.md`, `docs/TECHNICAL_DECISIONS.md` | Documentation review | Reviewed against implementation |
| O14 | Learning and future scope | Mandatory documentation | Candidate learning and factual improvement opportunities | `README.md`, `docs/TECHNICAL_DECISIONS.md` | Documentation review | Reviewed against implementation |
| O15 | Public GitHub repository; share link | Mandatory submission | Publish reviewed repository and supply its URL | External GitHub submission | Verify repository is public and evaluator can clone it | Public repository and fresh clone verified; candidate submits the link |

## Additional build requirements and implementation choices

These are user-requested robustness improvements or implementation policies. They are **not additional official minimum requirements**.

| ID | Enhancement / policy | Source and purpose | Responsible files | Relevant test/review target | Verification |
|---|---|---|---|---|---|
| E1 | MultiPolygon, MultiLineString, holes | User request; natural extension of Shapely operations | `app/services/measurement.py` | `test_analytic_metric_area_including_holes_and_multipart`, `test_analytic_metric_lengths` | Verified by full suite |
| E2 | Per-feature measurement method, CRS, units, status and reason | Implementation choice; results remain interpretable | `app/schemas.py`, `app/services/measurement.py` | `tests/test_measurement.py`; `tests/test_api.py::test_kml_contract`, `test_shapefile_real_roundtrip` | Verified by full suite |
| E3 | Local extent at most 1° per axis, latitude 80°S–84°N; no antimeridian measurement | Implementation policy limiting projection misuse | `app/services/measurement.py` | `test_outside_policy_geometries_are_retained_without_false_measurement` | Verified by full suite |
| E4 | Preserve altitude but calculate in 2D | Explicit limitation | `app/services/measurement.py` | `test_altitude_preserved_but_excluded_from_horizontal_length` | Verified by full suite |
| E5 | Reject invalid/nonfinite coordinates, do not silently repair | User request; avoid misleading geometry | `app/services/measurement.py` | `test_non_measurable_feature_statuses_are_explicit`, `test_out_of_range_wgs84_coordinates_are_invalid`, `test_non_finite_geometry_is_not_serialized` | Verified by full suite |
| E6 | Secure, bounded uploads and ZIP extraction | User request; untrusted input defenses | `app/middleware.py`, `app/config.py`, `app/services/archive.py` | `tests/test_security.py::test_archive_paths`, `test_symlink_archive`, `test_ambiguous_dataset_and_duplicates`, `test_archive_bomb_and_nested_archive`, `test_archive_resource_limits`, `test_upload_limit`, `test_request_stream_limit_without_content_length` | Verified by full suite |
| E7 | KML entity defenses and parser limits | User request; avoid external entity and structural abuse | `app/services/parsing.py` | `tests/test_security.py::test_rejected_content`, `test_kml_resource_limits`; `tests/test_review_regressions.py::test_invalid_geometry_parser_exceptions_are_safe_client_errors`, `test_multiple_direct_geometries_cannot_silently_drop_a_geometry` | Verified by full suite |
| E8 | Require one dataset with `.shp`, `.shx`, `.dbf`, `.prj` | Implementation policy; no arbitrary dataset or CRS guesses | `app/services/archive.py`, `app/services/parsing.py` | `tests/test_security.py::test_missing_companions`, `test_ambiguous_dataset_and_duplicates`, `test_malformed_crs_and_wrong_signature`; `tests/test_review_regressions.py::test_broken_deflate_stream_is_a_safe_archive_error` | Verified by full suite |
| E9 | Persist metadata and results atomically in SQLite; remove temporary raw files | User request and retrieval semantics | `app/db.py`, `app/services/files.py`, `app/services/parsing.py` | `tests/test_api.py::test_restart_persistence`, `test_failures_leave_no_records`; `tests/test_security.py::test_transaction_rolls_back_metadata_and_features`, `test_temporary_cleanup_on_success_and_failure` | Verified by full suite |
| E10 | Stable UUIDs, structured errors, 201 upload and pagination | Implementation choices; documented API contract | `app/main.py`, `app/schemas.py`, `app/errors.py` | `tests/test_api.py::test_kml_contract`, `test_pagination_and_unknown_ids`, `test_openapi_and_health`, `test_wrong_request_fields` | Verified by full suite |
| E11 | Reproducible dependencies, lint, CI and container setup | User request; reviewer setup | `pyproject.toml`, lockfile, CI, Docker and compose files | Installation, Ruff, full Pytest, container build/start when available | Native installation and hosted Linux CI passed, including Compose build, HTTP checks and restart persistence |
| E12 | Interview preparation and adversarial review | User request | `docs/INTERVIEW_PREP.md`, delivery report | Review answers against code and actual test report | Reviewed against implementation |

## Differentiation-pass evidence

- Measurement evidence: `scripts/measurement_evidence.py --check` verifies 16 executed cases and the saved report/JSON.
- Properties: `tests/test_properties.py` verifies five invariants, with 40 accepted examples each in the recorded run.
- Failure gaps: `tests/test_final_regressions.py` covers KML singleton-child ambiguity, unsupported/native-unrecognized CRS, real multipart Shapefile limits, and unavailable transformations.
- Reviewer experience: `scripts/reviewer_demo.py` uses real HTTP, disposable storage, explicit numeric checks and safe rejection.
- Mandatory routes/schemas, the measurement engine, and runtime dependency lock are byte-identical to the pre-pass source archive. Only invalid KML structural acceptance became stricter.

## Contract and scope decisions

- Metres and square metres are selected units; the brief does not prescribe units.
- Geometry is returned in its source CRS with an accompanying CRS field. A projected geometry object must not be treated as RFC 7946 longitude/latitude GeoJSON.
- Uploaded files can complete with skipped features. Per-feature statuses distinguish unmeasurable geometry from an invalid entire file.
- Every supported measurable feature is reprojected, even if its source coordinates are already projected.
- The bounded UTM policy is an openly documented geographic coverage restriction. It does not claim a globally accurate area/length engine.
- UUIDs, SQLite, limits, Docker, tests, and pagination are chosen implementation details, not text attributed to the brief.
- This is a local unauthenticated evaluation service. External publication of code and public deployment of a running data API are separate actions.
