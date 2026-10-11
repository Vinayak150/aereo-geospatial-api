"""Validate every ZIP member; extract only one dataset to generated filenames."""

import io
import stat
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from app.config import Settings
from app.errors import APIError

COMPANIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def extract_shapefile(content: bytes, directory: Path, settings: Settings) -> Path:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_archive_entries:
                raise APIError("ARCHIVE_LIMIT", "Archive contains too many entries.", 413)
            names: dict[str, zipfile.ZipInfo] = {}
            declared_total = 0
            for entry in entries:
                name = entry.filename
                path = PurePosixPath(name)
                mode = entry.external_attr >> 16
                if (
                    not name
                    or "\\" in name
                    or ":" in name
                    or "\x00" in entry.orig_filename
                    or path.is_absolute()
                    or ".." in path.parts
                    or any(ord(char) < 32 for char in name)
                    or stat.S_ISLNK(mode)
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                ):
                    raise APIError("UNSAFE_ARCHIVE", "Archive contains an unsafe path or entry.")
                key = str(path).casefold()
                if key in names:
                    raise APIError("AMBIGUOUS_ARCHIVE", "Archive contains duplicate paths.")
                names[key] = entry
                if entry.flag_bits & 1:
                    raise APIError("UNSAFE_ARCHIVE", "Encrypted archives are not supported.")
                if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise APIError(
                        "INVALID_ARCHIVE", "Only stored or DEFLATE ZIP members are supported."
                    )
                declared_total += entry.file_size
                if (
                    declared_total > settings.max_uncompressed_bytes
                    or entry.file_size / max(entry.compress_size, 1)
                    > settings.max_compression_ratio
                ):
                    raise APIError(
                        "ARCHIVE_LIMIT", "Archive expansion exceeds configured limits.", 413
                    )
                if path.suffix.lower() in {".zip", ".kmz", ".tar", ".gz", ".7z"}:
                    raise APIError("UNSAFE_ARCHIVE", "Nested archives are not supported.")
            candidates = [
                key for key, entry in names.items() if key.endswith(".shp") and not entry.is_dir()
            ]
            if len(candidates) != 1:
                raise APIError(
                    "AMBIGUOUS_DATASET", "ZIP must contain exactly one Shapefile dataset."
                )
            stem = candidates[0][:-4]
            for suffix in (".shp", ".shx", ".dbf", ".prj"):
                if stem + suffix not in names or names[stem + suffix].is_dir():
                    code = "MISSING_CRS" if suffix == ".prj" else "MISSING_COMPANION"
                    raise APIError(code, f"Shapefile requires a matching {suffix} file.")
            actual_total = 0
            # Read all members to check CRC and actual expansion, including ignored sidecars.
            for key, entry in names.items():
                if entry.is_dir():
                    continue
                suffix = PurePosixPath(key).suffix
                selected = key == stem + suffix and suffix in COMPANIONS
                target = directory / ("dataset" + suffix) if selected else None
                with archive.open(entry) as source:
                    output = target.open("wb") if target else None
                    try:
                        while chunk := source.read(64 * 1024):
                            actual_total += len(chunk)
                            if actual_total > settings.max_uncompressed_bytes:
                                raise APIError(
                                    "ARCHIVE_LIMIT", "Archive expansion is too large.", 413
                                )
                            if output:
                                output.write(chunk)
                    finally:
                        if output:
                            output.close()
            return directory / "dataset.shp"
    except APIError:
        raise
    except (
        zipfile.BadZipFile,
        zlib.error,
        RuntimeError,
        NotImplementedError,
        OSError,
        EOFError,
    ) as exc:
        raise APIError(
            "INVALID_ARCHIVE", "ZIP is corrupt or uses unsupported compression."
        ) from exc
