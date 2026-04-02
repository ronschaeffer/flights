"""ICAO hex code to aircraft registration/operator lookup.

Uses the tar1090-db community database (619K+ aircraft).
CSV format: hex;reg;type;flags;description;year;owner
Source: https://github.com/wiedehopf/tar1090-db
"""

from dataclasses import dataclass
import gzip
import logging
import os

from flights.config import BASE_DIR

logger = logging.getLogger(__name__)

HEX_DB_PATH = os.path.join(BASE_DIR, "data", "aircraft_hex.csv")
HEX_DB_GZ_PATH = HEX_DB_PATH + ".gz"

# Flag bit meanings (hex string, rightmost = bit 0)
_FLAG_MILITARY = 0x01
_FLAG_INTERESTING = 0x02
_FLAG_PIA = 0x04
_FLAG_LADD = 0x08


@dataclass(slots=True)
class HexEntry:
    """A single hex database entry."""

    hex_code: str
    registration: str
    type_code: str
    flags: int
    description: str
    year: str
    owner: str

    @property
    def is_military(self) -> bool:
        return bool(self.flags & _FLAG_MILITARY)


def load_hex_db(path: str | None = None) -> dict[str, HexEntry]:
    """Load the hex database from CSV into a dict keyed by uppercase hex code."""
    if path is None:
        # Prefer gzipped if available
        path = HEX_DB_GZ_PATH if os.path.exists(HEX_DB_GZ_PATH) else HEX_DB_PATH

    if not os.path.exists(path):
        logger.warning("Hex database not found at %s", path)
        return {}

    db: dict[str, HexEntry] = {}
    opener = gzip.open if path.endswith(".gz") else open

    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(";")
                if len(parts) < 4:
                    continue
                hex_code = parts[0].upper()
                try:
                    flags = int(parts[3], 16) if parts[3] else 0
                except ValueError:
                    flags = 0
                db[hex_code] = HexEntry(
                    hex_code=hex_code,
                    registration=parts[1] if len(parts) > 1 else "",
                    type_code=parts[2] if len(parts) > 2 else "",
                    flags=flags,
                    description=parts[4] if len(parts) > 4 else "",
                    year=parts[5] if len(parts) > 5 else "",
                    owner=parts[6] if len(parts) > 6 else "",
                )
        logger.info("Loaded hex database: %d entries", len(db))
    except Exception:
        logger.exception("Failed to load hex database from %s", path)

    return db
