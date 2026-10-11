# Interview preparation

Use the repository and test report while preparing. Explain the behavior and limitations you can demonstrate; do not describe unexecuted checks as passing.

1. **Why FastAPI rather than Django?**
   The deliverable is a small API. FastAPI supplies multipart uploads, typed validation, response models, and OpenAPI without an admin site or a larger web application structure. Django would also be viable; this choice keeps the submission's surface area small.

2. **Why cannot we call `geometry.area` on EPSG:4326 data?**
   Shapely uses Cartesian coordinates. On longitude/latitude input, the result is in square degrees, and a degree has no constant physical size. We transform supported local geometries to a metre-based UTM CRS before measuring.

3. **How do you select a measurement CRS?**
   I inspect each feature in WGS84, require at most one degree of extent on both axes within 80°S–84°N, then select a WGS84 UTM zone from its bounds midpoint and hemisphere. The response records that CRS. Broad, polar, and antimeridian-crossing features are skipped explicitly.

4. **Are the reported measurements exact physical dimensions?**
   No. They are planar horizontal measurements in a local projection. UTM introduces scale distortion, and altitude is ignored. Independent ellipsoid comparisons check representative cases using stated tolerances; they do not establish global or survey-grade accuracy.

5. **What happens when a Shapefile is already projected, or uses feet?**
   I still interpret its declared source CRS and transform to the chosen metric UTM CRS. This avoids treating arbitrary projected coordinates or feet as metres. A missing `.prj` is rejected rather than guessed, and `always_xy=True` keeps coordinate order explicit.

6. **How do you measure holes and multipart geometries?**
   Shapely subtracts polygon interior rings and sums MultiPolygon areas. MultiLineString length sums its component lines. Analytic tests include a rectangle with a hole, separate polygons, and 3–4–5 line segments. Mixed collections are retained but not measured.

7. **How do you handle invalid geometry without returning false numbers?**
   Null, empty, invalid, unsupported, out-of-policy, and failed-transformation cases have distinct statuses and null measurement fields. I do not silently repair shapes because repair can change their meaning. File completion is separate from whether each feature was measurable.

8. **How are malicious uploads constrained?**
   There are body/file limits, ZIP path and link checks, entry/expansion/ratio limits, CRC reads, generated extraction paths, and XML entity defenses. These reduce risk but native parsers may allocate before semantic checks. Public deployment would need isolated workers, concurrency/time limits, and access control.

9. **What prevents half-written uploads and how do restarts work?**
   The service parses and measures first, then inserts metadata and every feature in one SQLAlchemy transaction. Any persistence error rolls back the whole insert. Completed results live in SQLite and remain available after restart if the database is retained; temporary raw uploads are discarded.

10. **How do your tests establish correctness, and what would you improve next?**
    Analytic metric shapes test arithmetic independently, and PyProj Geod provides a separate ellipsoidal comparison for geographic cases. API, persistence, and adversarial tests exercise real parsers. Next steps depend on need: global measurement semantics, parser isolation, retention/migrations, and measured performance. See the actual test report for executed commands and results.

## Five follow-ups from the final review

1. **Why is the Geod difference not an absolute accuracy error?** UTM straight-edge planar measurements and shortest-edge ellipsoidal measurements use different models. Projection distortion, edge semantics and terrain assumptions differ; neither comparison establishes survey ground truth.
2. **When can multipart area fail to equal independently measured part areas?** If the aggregate and its parts select different measurement CRSs. The property test first asserts identical CRS selection before testing additivity.
3. **Why validate KML structure when FastKML already parses it?** Successful parsing did not guarantee completeness: repeated outer boundaries or coordinate blocks were silently discarded. Cardinality validation prevents wrong measurements from apparently successful uploads.
4. **Why keep broad features unsupported instead of forcing a projection?** A number without defensible projection semantics is worse than an explicit limitation. Expanding coverage requires a tested geodesic/equal-area policy and clarified edge/antimeridian semantics.
5. **What does the reviewer demo prove, and what does it not prove?** It proves real HTTP ingestion, retrieval, a known planar result, safe rejection and isolation/cleanup. It does not establish public-deployment security, worst-case memory, performance, container behavior or hosted CI success.
