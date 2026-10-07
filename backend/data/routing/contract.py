"""Immutable road graph identity, separate from the infrastructure POI baseline."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "routing"


@lru_cache(maxsize=1)
def load_manifest() -> dict:
    manifest = json.loads((ROOT / "car-v1.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((ROOT / "krasnoyarsk-car-v1.osm.pbf").read_bytes()).hexdigest()
    if manifest["pbf_sha256"] != digest or manifest["data_version"] != "mesto-car-v1-" + digest:
        raise ValueError("Routing snapshot checksum/identity mismatch")
    if manifest["endpoint_bounds"] != [92.4, 55.8, 93.2, 56.35] or manifest["engine_version"] != "5.27.1":
        raise ValueError("Unsupported routing dataset contract")
    return manifest
