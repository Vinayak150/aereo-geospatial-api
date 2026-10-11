"""Check record correspondence without decoding geometry or DBF field values."""

import struct
from pathlib import Path

from app.errors import APIError


def active_record_ids(path: Path, max_features: int) -> list[int]:
    """Return expected OGR FIDs, excluding DBF records marked as deleted.

    SHP has no record-count header. SHX defines indexed slots; DBF must have
    one row per slot, including deleted rows. Do not count sequential SHP
    blocks: in-place edits can leave obsolete geometry blocks before REPACK.
    """
    error = "Shapefile geometry, index and attribute records are inconsistent."

    def require(condition: bool) -> None:
        if not condition:
            raise APIError("INVALID_SHAPEFILE", error)

    with path.open("rb") as shp, path.with_suffix(".shx").open("rb") as shx:
        with path.with_suffix(".dbf").open("rb") as dbf:
            shp_size, shx_size, dbf_size = (
                path.with_suffix(suffix).stat().st_size for suffix in (".shp", ".shx", ".dbf")
            )
            require(shp_size >= 100 and shx_size >= 100 and dbf_size >= 32)
            shp_header, shx_header, dbf_header = shp.read(100), shx.read(100), dbf.read(32)
            for header, size in ((shp_header, shp_size), (shx_header, shx_size)):
                require(
                    header[:4] == b"\x00\x00\x27\x0a"
                    and struct.unpack_from(">I", header, 24)[0] * 2 == size
                )
            require((shx_size - 100) % 8 == 0)
            slots = (shx_size - 100) // 8
            records, header_size, record_size = struct.unpack_from("<IHH", dbf_header, 4)
            require(records == slots and header_size >= 33 and record_size >= 1)
            require(header_size + records * record_size <= dbf_size)
            if slots > max_features:
                raise APIError("FEATURE_LIMIT", "File contains too many features.", 413)
            active = []
            for fid in range(slots):
                offset_words, length_words = struct.unpack(">II", shx.read(8))
                offset, length = offset_words * 2, length_words * 2
                require(offset >= 100 and length >= 4 and offset + 8 + length <= shp_size)
                shp.seek(offset)
                require(struct.unpack(">II", shp.read(8))[1] == length_words)
                dbf.seek(header_size + fid * record_size)
                flag = dbf.read(1)
                require(flag in (b" ", b"*"))
                if flag == b" ":
                    active.append(fid)
            return active
