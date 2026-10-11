# Delivery report

Date: 2026-10-11. The implementation is publicly available on GitHub with verified author/committer attribution. Local release checks and hosted Linux CI pass, including Docker/Compose execution and restart persistence.

## Final release audit

The original four-page SharePoint brief was reopened and read in the browser for this release. Required formats, three endpoint paths, feature fields, projected polygon/line calculations, point behavior, and README deliverables match the implementation. No additional mandatory requirement or confidentiality notice appeared in the displayed brief. The public source contains normalized requirement notes, not the original company document; bundled datasets are synthetic.

Source review covered projection/axis/unit handling, holes and multipart geometry, invalid coordinates, extent policies, ZIP bounds and paths, KML singleton validation, entity protection, parser errors, transactions, cleanup and concurrency. No new substantive application defect was confirmed. Application code, measurement policy and test fixtures were preserved. The previously fixed silent KML data-loss regressions pass.

Release preparation corrected missing Git/Docker exclusions for alternative environments, database sidecars outside the data directory, temporary files, editor state and local secrets. The README now exposes stack, mandatory endpoints and quick execution earlier. CI now includes both HTTP entry points and Compose checks for both formats, actual measurements, UID, resource restrictions and restart persistence. CI configuration, shell syntax and embedded Python parsed successfully before publication. The hosted run subsequently executed and passed the container checks; results are recorded below.

### Verification repeated for this release

A new Python 3.12.13 environment on macOS ARM64 installed all 68 pinned development packages using binary wheels. Every installed version matches its pin; `python -m pip check` reports no broken requirements.

| Executed command | Actual result |
|---|---|
| `ruff check .` / `ruff format --check .` | Passed; 33 Python files formatted |
| `mypy app` | Passed; 12 source files |
| `pytest --cov=app --cov-report=term-missing --cov-fail-under=85 --hypothesis-show-statistics -q` | 111 passed; 95.28% statement coverage; one upstream Starlette deprecation warning |
| Property statistics in that run | Five properties, 40 accepted examples each, no failures; 17 discarded generation attempts in the line strategy |
| `python scripts/measurement_evidence.py --check` | 16 cases passed, including saved Markdown/JSON reproduction |
| `python scripts/reviewer_demo.py` | Actual HTTP uploads/retrieval, 200 m² reference, invalid-input rejection and cleanup passed |
| `python scripts/smoke.py` | Compatibility entry point independently executed and passed |
| `pip-audit -r requirements.lock --no-deps --disable-pip` | No known vulnerabilities found |
| `pip-audit -r requirements-dev.lock --no-deps --disable-pip` | No known vulnerabilities found |
| `docker info` | Cannot connect to the local Docker daemon after socket access was granted |
| `docker compose version` | Compose command/plugin unavailable |

Both audit commands additionally used a writable cache and disabled the progress spinner. Their advisory coverage does not establish absence of application defects or native-library vulnerabilities. No thresholds or tests were weakened.

A staged-files-only export was also relocated to a disposable directory. Evidence verification and both HTTP entry points passed there using the fresh environment, without untracked source files or development-machine paths. Conflicting inherited database/limit/worker/proxy settings did not affect the demo: an existing database sentinel remained unchanged and temporary directories were empty after each run. An injected demonstration failure also exited nonzero and cleaned up. A subsequent fresh clone of the published repository also passed evidence verification and the real HTTP demo.

### Publication and attribution

The implementation was published to [Vinayak150/aereo-geospatial-api](https://github.com/Vinayak150/aereo-geospatial-api), a public repository on `main`, without force-pushing. Initial implementation commit: `7af7bc493a538f8cd93d71899765db6132e65a47` (`feat: implement geospatial file measurement API`).

GitHub CLI authentication was checked, the account was confirmed as `Vinayak150`, and GitHub's email API reported the authorized email as verified and primary before committing. Local author and committer were configured as Vinayak Mahindrakar. GitHub's commit API links both identities to `Vinayak150`; the complete commit message contains no co-author trailers. The Contributors API lists only `Vinayak150` at this checkpoint. No author/committer environment overrides or active local Git hooks were found. CI does not create commits. Existing third-party dependency attribution was not changed.

The application has its own Git repository; the unrelated parent Documents repository/history remains untouched. All 46 staged files and the diff were reviewed. Secret-pattern and personal-path scans found no matches; the only binary is the documented synthetic Shapefile ZIP. Environment files, databases, caches, editor state and generated archives are excluded; `.env.example` and the required sample ZIP remain tracked.

A fresh clone of the public `main` branch was checked against the implementation SHA. The evidence verifier and actual HTTP reviewer demonstration both passed from that clone using the previously clean-installed dependency environment. The external application form has not been submitted.

### Hosted release verification

[Verify run 38125363468](https://github.com/Vinayak150/aereo-geospatial-api/actions/runs/38125363468) completed with **success** for implementation commit `7af7bc493a538f8cd93d71899765db6132e65a47`; the `verify` job and all steps succeeded. Actual logs confirm **111 passing tests**, **95.28% coverage**, **16 evidence cases**, and five properties with **40 accepted examples each**. Installation on the fresh Linux runner, dependency consistency, Ruff, formatting, mypy, both real HTTP commands and the development/runtime dependency audit all passed; the audit reported no known vulnerabilities.

The Compose step built the image, started the service, exercised KML and Shapefile upload/retrieval, verified the 200 m² reference and safe invalid-input rejection, checked non-root UID 10001, read-only root filesystem, 512 MiB memory, one CPU, 64-process limit, dropped capabilities and no-new-privileges. Stored metadata and measurements remained identical after restart. The disposable container and volume were removed after the check. No failing checks were skipped or disabled.

A subsequent documentation-only commit records these results; its own run is available from the [workflow history](https://github.com/Vinayak150/aereo-geospatial-api/actions/workflows/ci.yml). The implementation and workflow are unchanged by that documentation update.

**Verdict: READY TO SUBMIT.** The public implementation, commit attribution, fresh-clone reviewer experience and required checks are verified. The documented local-UTM/2D measurement scope and absence of public-service authentication remain intentional limitations; this is assignment readiness, not a survey certification or a claim of public-deployment readiness. The candidate still needs to submit the repository link and required personal details through Aereo's form.

## A. Requirements compliance

The [requirements matrix](REQUIREMENTS.md) maps each official requirement to code, named tests and verification status. The four-page brief was read before implementation; [normalized notes](OFFICIAL_ASSIGNMENT.md) distinguish official requirements from additional user-requested engineering work.

Implemented: FastAPI, KML and zipped Shapefile upload, required feature inspection fields, polygon area, line length, point handling, projected-CRS calculations, all three official endpoint paths, README setup/API/architecture/decisions/learning/future scope. Measurements have a documented geographic coverage restriction, not a global accuracy claim.

The required public repository is available at [Vinayak150/aereo-geospatial-api](https://github.com/Vinayak150/aereo-geospatial-api). The application form has not been submitted.

## B. Architecture

The HTTP layer validates requests and serializes Pydantic responses. A body-limiting middleware runs before multipart parsing. Ingestion coordinates archive validation, established GIS parsers, per-feature measurement and one atomic database transaction. SQLite stores metadata and feature results; read endpoints reuse those records. Raw files are discarded after processing.

This structure needs no external database service, queue or cloud account. The user workspace had no existing application code. Work was scoped to this new project directory; the existing parent Documents Git repository was not initialized, reset, committed or reconfigured.

## C. Implementation inventory

The initial build created the following components; the targeted changes are listed below:

- `app/`: configuration, errors, API factory, schemas, SQLite models, body-limit middleware.
- `app/services/`: archive validation/extraction, KML/Shapefile parsing, measurement policy, ingestion/persistence.
- `tests/`: fixtures, API integration tests, measurement correctness tests, security tests, regression tests, bundled sample checks.
- `sample_data/`: synthetic Bengaluru KML and a genuine zipped projected Shapefile with a 200 m² rectangle.
- `scripts/`: sample generator and real-server smoke test.
- `docs/`: official reading notes, requirements matrix, technical decisions, interview preparation, this report.
- `README.md`, `pyproject.toml`, runtime/development lockfiles, `.python-version`, `.env.example`, `.gitignore`, `.dockerignore`, `Dockerfile`, `compose.yaml`, `.github/workflows/ci.yml`.

## D. Executed verification

Environment: macOS ARM64, Python 3.12.13. Commands below run from the project directory with the development environment active.

| Check | Command | Observed result |
|---|---|---|
| Complete suite, including integration tests | `pytest --cov=app --cov-report=term-missing --cov-fail-under=85 -q --tb=short --hypothesis-show-statistics` | **111 passed**, **95.28%** statement coverage |
| Lint | `ruff check .` | Passed |
| Formatting | `ruff format --check .` | Passed; 33 files formatted |
| Types | `mypy app` | Passed; 12 source files |
| Clean second environment | `python -m pip install --only-binary=:all: -r requirements-dev.lock` | Initial build installed 67 pinned packages in a clean environment. This pass adds Hypothesis and updates pip; all 68 current pins were checked against the verification environment. |
| Dependency consistency | `python -m pip check` | No broken requirements |
| Editable package | `python -m pip install --no-deps -e .` | Built and installed successfully |
| Real HTTP reviewer demo | `python scripts/reviewer_demo.py` | Passed: uploads, metadata equality, measurements, units/CRS, **200.0 m²**, safe 422 rejection, surviving valid records and cleanup |
| Demo isolation and failure cleanup | Subprocess harness with an existing database sentinel, conflicting inherited limits/worker count/proxy, and a separate injected demonstration failure | Successful HTTP run left sentinel unchanged and temporary directory empty; injected failure exited nonzero and also cleaned temporary resources |
| Independent evidence | `python scripts/measurement_evidence.py --check` | **16 cases passed**: 13 numeric comparisons and 3 explicit policy exclusions; Markdown/JSON reproduction checked |
| Property tests | `pytest tests/test_properties.py --hypothesis-show-statistics` (also included in full suite) | **5 properties × 40 accepted examples**, no failing examples; generated examples are not counted as 200 extra pytest tests |
| Runtime + development vulnerability database | `pip-audit -r requirements-dev.lock --no-deps --disable-pip --progress-spinner off --cache-dir <writable-cache>` | Initial audit found advisory PYSEC-2026-3721 for pip 26.1.2 (listed twice by the feed); after updating to 26.2.1, **no known vulnerabilities found** |
| YAML syntax | Ruby standard-library YAML parser for Compose and Actions files | Both parsed successfully after fixing a quoted-colon issue in CI |
| Container daemon availability | `docker info` | Failed: local Docker daemon unavailable |
| Compose availability | `docker compose config --quiet` | Could not execute: Compose plugin unavailable |

The test suite emitted one upstream Starlette deprecation warning about the HTTPX TestClient compatibility path. The tests pass with the pinned versions; no test warning was hidden in the reported coverage run. Shapely's deprecated transformation API was replaced during review.

Coverage is evidence of exercised statements, not proof of correctness or absence of vulnerabilities. The audit covers published Python-package advisories, not exhaustive native-library or application security testing. The original local Docker attempt was unavailable. Hosted GitHub Actions subsequently passed the image build, Compose startup, real HTTP checks and restart persistence; see the release verification section above.

### Adversarial review outcomes

Review found and fixed malformed KML and invalid geometry exceptions returning 500, multiple direct KML geometries silently dropping data, corrupt DEFLATE streams returning 500, and UTC timestamps changing on retrieval. Regression tests reproduce each case and now pass. Ring closure is explicitly validated to avoid implicit repair.

Security tests cover traversal paths, symlinks, duplicate archives, ambiguous datasets, missing companions, invalid CRS/signatures, compression bombs, nested archives, entity declarations, invalid encodings, XML/feature/coordinate limits, request streaming without Content-Length, temporary cleanup and transactional rollback. Concurrent/repeated uploads and restart persistence are tested. GIS tests use real library calculations, analytic references and independent ellipsoidal comparisons.

## E. Demonstrable strengths

- Correctness is tied to known geometry and independent references, including holes, multipart shapes, southern hemisphere, zone edges and feet conversion.
- Source geometry and metadata accompany interpretable measurements and skip reasons.
- File parsing and persistence failures leave no partially committed upload.
- Safety checks apply to full request bodies and every ZIP member, not just extensions or advertised sizes.
- Setup needs only Python and binary dependencies; useful sample data and a real-server smoke command are included.

## F. Known limitations

- Per-feature extent ≤1° on each geographic axis, latitude 80°S–84°N. Extensive, polar and antimeridian-crossing geometries are not measured.
- Planar 2D UTM measurements, not exact geodesic or terrain measurements. No edge densification. Comparison tolerances do not establish a global error guarantee.
- Offline datum transformation resources may be unavailable; no guessed fallback.
- Partial KML metadata fidelity; no remote links, models, tracks or archive KMZ support.
- SQLite/local evaluation scope; no authentication, ownership, retention/delete API, migrations or distributed workers.
- Input limits and documented concurrency controls do not isolate native parsers or impose a per-job CPU deadline. No performance benchmark is claimed.
- Version-pinned dependencies are not hash-locked, and the container base is not digest-pinned.
- Docker is unavailable on the original Mac; Linux Docker/Compose behavior and hosted CI were verified successfully.

## G. Fresh-reviewer execution

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==26.2.1
python -m pip install --only-binary=:all: -r requirements-dev.lock
python -m pip check
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
python scripts/measurement_evidence.py --check
python scripts/reviewer_demo.py
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --limit-concurrency 8
```

Use the sample cURL commands in the README. From a Docker-capable host, also run `docker compose up --build -d`, upload both samples, restart the service and verify retrieval with the same IDs.

## H. Submission checklist

- [x] Official brief reviewed and traced to implementation.
- [x] Native implementation, math, integration, adversarial tests and documentation reviewed.
- [x] Sample files, explicit limitations and interview material included.
- [x] Build/run Docker on the hosted runner; verify Compose behavior and volume persistence.
- [x] Publish the project contents to the specified public GitHub repository with the authorized attribution.
- [x] Verify the successful hosted CI run and the reviewer workflow from a fresh public clone.
- [ ] Review and understand the code, then submit the public repository URL, resume link and candidate details through Aereo's form.

## I. Interview preparation

[INTERVIEW_PREP.md](INTERVIEW_PREP.md) contains ten foundation questions and five deeper follow-ups with concise answers covering framework choice, parsing, CRS and units, projection policy, holes and multipart shapes, invalid geometry, file security, persistence, API contracts and future scaling. [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) develops the reasoning and alternatives. Use these to explain and modify the actual implementation, not to memorize claims beyond its scope.

## Targeted differentiation pass

The baseline was rerun before changes: **97 tests, 93.84% coverage**. After the pass: **111 tests, 95.28% coverage**. Fourteen additional pytest cases comprise nine focused regression/failure cases and five property tests. Test counts alone are not the differentiator; the evidence is inspectable numerical references and demonstrated rejection of silently ambiguous input.

### Audited gaps and decisions

| Category | Actual gap | Action |
|---|---|---|
| Correctness | FastKML accepted repeated polygon outer boundaries or line coordinate blocks and retained only the first | Validate singleton geometry children before parsing; four real malformed-KML regression cases verify 422 and no saved record |
| Security/reliability | Broader development audit found the old pip pin; the smoke script inherited unrelated Aereo limits | Update pip pin/bootstrap to 26.2.1; demo always uses its own defaults/database, one worker, and direct loopback HTTP |
| Verification | Fixed references existed, but no generated evidence artifact or property suite; unsupported-CRS and Shapefile semantic limit branches lacked focused tests | Add generated Markdown/JSON evidence, five deterministic properties, real engineering/geocentric CRS and multipart limit tests, and injected missing-transform failure |
| Reviewer experience | Previous smoke test skipped GET metadata and invalid-upload demonstration | One-command HTTP demo verifies every required operation and safe rejection, prints units/CRS and cleans up |
| Unnecessary features | UI, global measurement fallback, PostGIS, queues, additional runtime services | Not added; existing architecture and measurement policy retained |

A failed intermediate CRS test exposed a test assumption: GDAL drops geocentric Shapefile CRS metadata, yielding `MISSING_CRS`, while it preserves a local engineering CRS, yielding `UNSUPPORTED_CRS`. Both are safe rejections. The final tests assert those observed policies rather than inventing a parser capability or changing valid API behavior.

### New and modified files

New: `scripts/__init__.py`, `scripts/measurement_evidence.py`, `scripts/reviewer_demo.py`, `tests/test_properties.py`, `tests/test_final_regressions.py`, `docs/MEASUREMENT_EVIDENCE.md`, `docs/MEASUREMENT_EVIDENCE.json`.

Modified: `app/services/parsing.py` (the only application source changed), `scripts/smoke.py` (compatibility alias), `requirements-dev.lock`, `.gitignore`, `Dockerfile` (patched pip bootstrap), `.github/workflows/ci.yml`, `README.md`, and the existing requirements, technical-decisions, interview-preparation and delivery-report documents.

Routes, response schemas, the measurement engine and runtime dependency lock were compared byte-for-byte against the pre-pass archive and remained unchanged. Stricter rejection of structurally ambiguous KML is intentional.

### Numerical evidence

Executed planar references produce **200 m²**, **190 m² with a hole**, **125 m² multipart area**, and **5 m line length**; the US-survey-foot source produces **200 m²**. All 16 evidence cases meet their predefined numeric or policy criteria. The largest observed geographic area model difference is approximately **0.19631220%** in the near-extent case. It is a planar/geodesic model difference, not a universal error bound or survey certification. [The generated report](MEASUREMENT_EVIDENCE.md) supplies actual results, references, differences, CRS and tolerances; the companion JSON records exact fixture coordinates.

### Evaluator review

| Question | Evidence-based assessment |
|---|---|
| Engineering thought beyond framework code? | Projection bounds, preserved source CRS, independent references, cardinality validation, atomic persistence and explicit skip reasons are visible in code and tests. |
| Major correctness claims independently verifiable? | Analytic fixtures and Geod comparisons are executable; saved numbers are checked for drift. These establish the documented cases, not every possible input or external survey truth. |
| Easy for another engineer to run? | Pinned dependencies, included genuine format samples, and one HTTP demo command. Fresh public clone and hosted Docker/Compose checks passed. |
| Defensible choices? | UTM meets the projected-measurement brief; SQLite and bounded synchronous ingestion fit retrieval by file ID. Property tests assert shared-CRS premises before additivity. |
| Transparent limitations? | Coverage restrictions, projection/model differences, native-parser resource risk, incomplete KML fidelity and missing public-deployment controls are explicit. |
| Realistic failure coverage? | Corrupt inputs, silent-parser-loss regressions, native CRS behavior, resource boundaries, unavailable transformations and atomic rollback are exercised. This is not exhaustive fuzzing. |
| Unnecessary maintenance burden? | No runtime services or unrelated features were added. Hypothesis is development-only; the old smoke entry point delegates to the same demo rather than duplicating its logic. |
| Consistent with the assignment? | Required formats, endpoints, fields and projected measurements remain; enhancements verify the existing scope. Public source publication is complete; the candidate submits the application link. |

**GitHub readiness:** the implementation is public, author/committer attribution is verified, and native plus hosted Docker/Compose checks passed. The repository is ready for submission within its documented scope. No hiring outcome or comparative candidate score is predicted.

Five questions about the hardest decisions, with concise answers, are appended to [INTERVIEW_PREP.md](INTERVIEW_PREP.md): model differences, same-CRS additivity, parser completeness, geographic coverage, and what the HTTP demonstration proves.
