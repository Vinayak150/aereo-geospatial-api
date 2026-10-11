"""Review the real HTTP API using a disposable server and database."""

import math
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def demonstrate(client: httpx.Client) -> None:
    print("PASS: isolated service is healthy. Port, UUIDs and timestamps are dynamic.")
    identifiers = []
    for name, count in (("bengaluru.kml", 3), ("reference_rectangle.zip", 1)):
        with (ROOT / "sample_data" / name).open("rb") as file:
            response = client.post("/api/files/", files={"file": (name, file)})
        require(
            response.status_code == 201, f"Upload failed: {response.status_code} {response.text}"
        )
        uploaded = response.json()
        identifier = uploaded["id"]
        identifiers.append(identifier)
        metadata = client.get(f"/api/files/{identifier}/")
        require(
            metadata.status_code == 200 and metadata.json() == uploaded,
            "Metadata changed on retrieval.",
        )
        require(
            uploaded["feature_count"] == count and uploaded["status"] == "COMPLETED",
            "Unexpected feature count/status.",
        )
        response = client.get(f"/api/files/{identifier}/measurements/")
        require(response.status_code == 200, "Measurement retrieval failed.")
        result = response.json()
        require(
            result["file_id"] == identifier and result["total"] == count,
            "Measurement envelope mismatch.",
        )
        require(len(result["features"]) == count, "Unexpected page length.")
        print(
            f"PASS: POST {name} → 201; GET metadata/results → 200; id={identifier}; features={count}"
        )
        for feature in result["features"]:
            if feature["status"] == "MEASURED":
                area = feature["area_m2"] is not None
                value = feature["area_m2"] if area else feature["length_m"]
                require(
                    value is not None and math.isfinite(value) and value > 0, "Invalid measurement."
                )
                require(
                    feature["measurement_crs"] == "EPSG:32643"
                    and feature["method"] == "planar_local_utm",
                    "Unexpected CRS/method.",
                )
                print(
                    f"  {feature['feature_id']}: {value:.9f} {'m²' if area else 'm'}; CRS={feature['measurement_crs']}"
                )
            else:
                require(feature["status"] == "NO_MEASUREMENT", "Unexpected skipped feature.")
                print(f"  {feature['feature_id']}: NO_MEASUREMENT (point)")
        if name.endswith(".zip"):
            require(
                math.isclose(result["features"][0]["area_m2"], 10 * 20, rel_tol=0, abs_tol=1e-6),
                "Reference rectangle failed.",
            )
            print("PASS: 10 m × 20 m reference = 200 m², tolerance 1e-6 m².")
    invalid = client.post("/api/files/", files={"file": ("invalid.kml", b"<not-kml/>")})
    require(
        invalid.status_code == 422 and invalid.json()["error"]["code"] == "INVALID_KML",
        "Invalid upload was not safely rejected.",
    )
    print(f"PASS: invalid KML → {invalid.status_code}; {invalid.json()}")
    require(
        all(
            client.get(f"/api/files/{identifier}/").status_code == 200 for identifier in identifiers
        ),
        "Invalid upload affected existing records.",
    )
    require(
        client.get("/docs").status_code == 200 and client.get("/openapi.json").status_code == 200,
        "API documentation unavailable.",
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aereo-smoke-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("AEREO_")
        }
        environment.update(AEREO_DATABASE_URL=f"sqlite:///{directory}/test.db", PROJ_NETWORK="OFF")
        with open(Path(directory) / "server.log", "w+") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:create_app",
                    "--factory",
                    "--workers",
                    "1",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--limit-concurrency",
                    "8",
                ],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=log,
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False
                ) as client:
                    for _ in range(100):
                        if process.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(log.read())
                        try:
                            if client.get("/health").status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Server did not become healthy within ten seconds.")
                    demonstrate(client)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    print("PASS: server stopped and temporary database/files removed.")


if __name__ == "__main__":
    main()
