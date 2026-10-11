# Official assignment — normalized reading notes

**Source:** [Aereo: Geospatial File Measurement API](https://ausindia-my.sharepoint.com/:w:/g/personal/gaurav_k_aereo_io/IQA-StSsm-LtRZ-g2y2_w7PpAQyEZxJY4tLIznWCOh9t2zs?e=50cxu9).

All four pages of the linked brief were read in the browser before application coding. The following preserves the substance and sequence of that reading in normalized Markdown. It is a working requirement record, not a verbatim facsimile or a replacement for the original. Formatting and prose have been normalized; the original document remains authoritative.

## Geospatial File Measurement API

### Problem statement and objective

Build a backend service using Django or FastAPI that accepts a geospatial file, processes its features, and returns measurement information. Accept Shapefile or KML data.

The objective is to evaluate clean backend API development, work with geospatial data, file processing, and production-quality Python. Architectural and implementation decisions beyond the minimum requirements are open to the candidate.

### Minimum requirements

1. **Backend framework.** Choose either Django with Django REST Framework or FastAPI.

2. **File upload.** Provide an endpoint that accepts a geospatial file. The example endpoint is `POST /api/files/`. Accept a `.zip` containing a Shapefile or a `.kml` file.

3. **File processing.** Read the uploaded geospatial data and extract its features. Identify at least each feature's ID/index, geometry type, geometry, CRS, and properties/attributes. Unsupported measurement geometry types should be handled gracefully instead of crashing the application.

4. **Measurements.** Calculate area for Polygon, length for LineString, and no measurement for Point.

5. **CRS handling.** Correctly handle geographic coordinates such as EPSG:4326. Do not directly calculate area or distance using latitude/longitude degrees. Transform geometry into an appropriate projected coordinate system before calculating measurements. The candidate may choose the projected CRS selection strategy.

6. **API design.** Provide at least the following APIs:

   | Operation | Endpoint | Behavior |
   |---|---|---|
   | Upload | `POST /api/files/` | Upload and process a file. |
   | File information | `GET /api/files/{id}/` | Return information about the uploaded file. |
   | Measurements | `GET /api/files/{id}/measurements/` | Return measurement results for features in the file. |

   The file-information example in the brief is:

   ```json
   {
     "id": "abc123",
     "filename": "survey.kml",
     "feature_count": 120,
     "crs": "EPSG:4326",
     "status": "COMPLETED"
   }
   ```

7. **Documentation.** Include a `README.md` explaining local setup, API endpoints with example requests/responses, application structure, file-processing flow, measurement-calculation flow, CRS handling, and important design decisions with alternatives considered.

8. **Submission.** Submit a public GitHub repository and share its link. Include learning and future scope in the README.

## Interpretation boundaries

The brief does not prescribe UUID identifiers, HTTP status codes, an error JSON schema, measurement units, a database, authentication, a test framework, Docker, asynchronous jobs, a frontend, or geodesic calculations. Choices in those areas are implementation decisions or additional requirements from the candidate's build request. The sample `abc123` identifier is illustrative, not a requirement to use that literal ID or a specific identifier type.

This implementation chooses UUIDs, metre/square-metre units, structured feature statuses, SQLite persistence, and bounded synchronous ingestion. It extends geometry support to MultiPolygon and MultiLineString. Its local UTM extent restrictions and `.prj` requirement are disclosed implementation policies; they were not supplied as official assignment restrictions. See [requirements traceability](REQUIREMENTS.md) and [technical decisions](TECHNICAL_DECISIONS.md).
