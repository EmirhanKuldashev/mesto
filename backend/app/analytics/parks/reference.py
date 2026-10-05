"""Frozen reviewed calibration; exact packaged bytes, never a database refit."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from app.analytics.parks.models import EvidenceModel, SnapshotIdentity, GeometrySnapshotIdentity

NORMALIZATION_VERSION = "parks-krasnoyarsk-relative-v1"
SAMPLING_VERSION = "parks-district-territorial-grid250-v1"
REFERENCE_ID = "parks-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-geometry-cdf-v1"
REFERENCE_PATH = Path(__file__).resolve().parents[3] / "data/fixtures/analytics/parks-krasnoyarsk-relative-v1.json"
# Whole-file SHA256 is pinned outside the artifact (no self-referential digest).
REFERENCE_SHA256 = "db3ba8ccedb1ff83c5c34fdca3346c48dd02c75260e6c448d155a39271a15fec"
DISTANCES_SHA256 = "1ce2594e12ee487bd7f0fd62f4c76237487ccc915fbc6c00023addef9a4b78a8"


class DistrictReference(EvidenceModel):
    slug: str
    geometry_ewkb_md5: str = Field(pattern=r"^[0-9a-f]{32}$")
    sample_count: int = Field(ge=180)


class ReferenceContract(EvidenceModel):
    contract_version: Literal["parks-calibration-reference-v1"]
    normalization_version: Literal["parks-krasnoyarsk-relative-v1"]
    reference_id: Literal["parks-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-geometry-cdf-v1"]
    reference_city: Literal["Krasnoyarsk"]
    scope_id: Literal["krasnoyarsk"]
    evidence_version: Literal["parks-evidence-v1"]
    eligibility_version: Literal["parks-osm-eligibility-v1"]
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"]
    sampling_version: Literal["parks-district-territorial-grid250-v1"]
    cdf_method: Literal["empirical-midrank-no-interpolation-v1"]
    sample_count: Literal[6065]
    distances_sha256: Literal["1ce2594e12ee487bd7f0fd62f4c76237487ccc915fbc6c00023addef9a4b78a8"]
    distances_m: tuple[float, ...]
    osm_snapshot: SnapshotIdentity
    park_geometry_snapshot: GeometrySnapshotIdentity
    geometry_fixture_sha256: Literal["7ac78515978087c0ba0272eaa427731473ee63421019eb962aa7e449c18e37a2"]
    districts: tuple[DistrictReference, ...]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def accepted_distribution(self):
        # This byte representation is exactly the accepted research value digest.
        digest = hashlib.sha256(json.dumps(list(self.distances_m), separators=(",", ":"),
                                          allow_nan=False).encode()).hexdigest()
        if (len(self.distances_m) != self.sample_count or
                tuple(sorted(self.distances_m)) != self.distances_m or
                any(d < 0 for d in self.distances_m) or digest != DISTANCES_SHA256 or
                len(self.districts) != 7 or len({d.slug for d in self.districts}) != 7 or
                sum(d.sample_count for d in self.districts) != self.sample_count or
                self.osm_snapshot.snapshot_version != "fresh-20261004T132116Z" or
                self.osm_snapshot.dataset_key != "osm-poi" or
                self.osm_snapshot.query_version != "osm-poi-query-v1" or
                self.osm_snapshot.query_hash != "5dd8b0b1555d83e35b3694375fbb595ef62074ff1545065f1779d5e8e6df0c09" or
                self.osm_snapshot.foundation_eligibility_version != "osm-poi-eligibility-v1" or
                self.osm_snapshot.scope_id != self.scope_id or
                self.osm_snapshot.canonical_checksum != "c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7"):
            raise ValueError("Accepted frozen reference identity/distribution mismatch")
        return self


@dataclass(frozen=True)
class LoadedReference:
    contract: ReferenceContract
    checksum: str


class ReferenceError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def read_reference(path: Path = REFERENCE_PATH) -> LoadedReference:
    """Fail closed on unavailable/corrupt bytes; no collection or regeneration."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ReferenceError("reference_unavailable") from exc
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ReferenceError("reference_checksum_mismatch")
    try:
        contract = ReferenceContract.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise ReferenceError("reference_version_or_contract_mismatch") from exc
    return LoadedReference(contract, REFERENCE_SHA256)
