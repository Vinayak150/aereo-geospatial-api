# Targeted data-integrity audit

Baseline: `46cd7d5225777380a787c62daf6c797ac5b9d8a6`. Executed on Python 3.12.13 with **Pyogrio 0.13.0 and bundled GDAL 3.12.4** on macOS ARM64. Every installed runtime/development version was compared to `requirements-dev.lock`; no dependency was changed. [Recorded before/after observations](DATA_INTEGRITY_EVIDENCE.json) come from actual Uvicorn HTTP requests and subsequent retrieval from disposable SQLite storage.

## Shapefile reproduction

The existing `shape_entries` fixture generated a real projected polygon dataset. Its geometry and fields were appended using `pyogrio.raw.write(..., append=True)` to create two indexed features. `zip_bytes` packaged the companion files. For the reported defect, **only DBF bytes 4–7** were changed from little-endian record count 2 to 1; the ZIP was regenerated with valid CRCs. The geometry and index files and all other DBF bytes were unchanged.

The original SHP is 372 bytes, matching its declared length. A sequential walk of this freshly generated file finds two geometry records. SHP has **no record-count header**: its length is not a feature count. The SHX contains two 8-byte entries after its 100-byte header. The DBF physically contains two row slots.

| Fixture | SHP records / SHX slots | DBF declared rows | `read_info` count | `raw.read` FIDs | Before fix | After fix |
|---|---|---:|---:|---|---|---|
| Valid | 2 / 2 | 2 | 2 | `[0, 1]` | 201; two persisted | 201; two persisted |
| DBF underreports | 2 / 2 | 1 | 2 | `[0]` | **201; one persisted, no reader exception** | **422 `INVALID_SHAPEFILE`** |
| DBF overreports | 2 / 2 | 3 | 2 | `[0, 1]` | 201 despite inconsistent metadata | 422 `INVALID_SHAPEFILE` |
| First DBF row deleted | 2 / 2 | 2 | 2 | `[1]` | 201; surviving FID 1 | Same valid behavior |
| Last DBF row deleted | 2 / 2 | 2 | 2 | `[0]` | 201; surviving FID 0 | Same valid behavior |
| Both DBF rows deleted | 2 / 2 | 2 | 2 | `[]` | 422 `EMPTY_DATASET` | Same existing empty-dataset policy |

The suspected silent loss **does reproduce with the pinned version**. A blanket comparison of `read_info()["features"]` with returned rows would be incorrect: the deletion controls show that this driver's metadata count includes slots that iteration legitimately skips.

## Validation strategy

The small `app/services/shapefile_integrity.py` helper checks SHP/SHX declared file lengths, SHX entry alignment, indexed geometry record bounds/content lengths, DBF header count/row availability and deletion flags. DBF declared rows must equal SHX slots **including deleted rows**. The existing feature limit bounds those slots before iteration.

It derives the expected active zero-based FIDs from DBF flags and checks that Pyogrio returns exactly those FIDs in order. This catches omissions without relying on driver feature-count semantics. It does not decode geometry or attribute values, replace GDAL, or silently repair inputs. It follows SHX offsets rather than requiring a packed sequential SHP layout, so obsolete geometry blocks left by edits remain acceptable. The DBF EOF byte is optional. A completely deleted dataset retains the existing `EMPTY_DATASET` behavior.

This is a record-correspondence check, not a full independent implementation of either binary format. Non-indexed obsolete SHP blocks are not treated as active features. Native-parser resource limits and other documented constraints remain.

## KML attribute reproduction

Four real uploads were tested: repeated `Data` names, repeated `SimpleData` names within one schema, matching names in distinct `SchemaData` elements, and a `Data`/`SimpleData` collision. All returned **201** before the fix and stored only `{"site": "second"}`, losing `first`.

Insertion now detects an existing key and rejects the entire upload with **422 `INVALID_KML`** and the fixed message `ExtendedData names must be unique within each feature.` The existing flat `properties.extended_data` schema is preserved. Distinct schemas may legitimately reuse field names in KML; this API explicitly rejects such collisions because its flat representation cannot preserve both values. This is an API representation restriction, not a claim that all such KML is invalid under the standard. Names remain scoped to each feature.

## Regression and verification evidence

`tests/test_data_integrity.py` adds 18 deterministic cases: two DBF count mismatches; six damaged row/index/flag cases; four valid deletion/EOF controls; an unrepacked geometry layout; a simulated reader omission after a real native read; and the four reproduced KML collisions. Rejection tests check both metadata and feature tables for zero partial persistence. Exact fixed error messages do not echo filenames, paths or attribute values. KML rejection also includes an earlier valid Placemark in the same upload, ensuring file-level atomicity.

```bash
pytest tests/test_data_integrity.py -q
pytest --cov=app --cov-report=term-missing --cov-fail-under=85 --hypothesis-show-statistics
python scripts/measurement_evidence.py --check
python scripts/reviewer_demo.py
python scripts/smoke.py
```

Executed local full suite: **129 passed, 95.45% statement coverage** (baseline 111 / 95.28%). All 16 measurement evidence cases and five properties with 40 accepted examples each still pass. Ruff, formatting, mypy, dependency consistency and both dependency audits pass. The original real-HTTP reproduction was repeated after the fix, producing the last column above. See the [hosted workflow history](https://github.com/Vinayak150/aereo-geospatial-api/actions/workflows/ci.yml) for the check associated with this commit; the earlier release's green run alone does not validate these changes.

Endpoints, response schemas, measurement calculations, dependency pins and the persistence architecture are unchanged.

## Primary format references

- [Esri Shapefile Technical Description](https://www.esri.com/library/whitepapers/pdfs/shapefile.pdf): geometry/attribute record correspondence, SHP record headers and SHX offsets/lengths (technical-description pages 2–5 and 23–25).
- [dBASE file structure](https://www.dbase.com/Knowledgebase/int/db7_file_fmt.htm): count/header/record-length fields and active/deleted record markers.
- [GDAL Shapefile driver](https://gdal.org/en/stable/drivers/vector/shapefile.html): deleted rows are skipped; REPACK removes obsolete storage; optional DBF EOF handling.
- [Pyogrio API reference](https://pyogrio.readthedocs.io/en/latest/api.html#pyogrio.read_info): feature counts are driver metadata and may be unavailable for some drivers. The concrete observations above were made with the pinned installed version.
