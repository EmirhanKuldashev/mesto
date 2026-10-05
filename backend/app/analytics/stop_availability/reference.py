"""Frozen reviewed calibration; exact packaged bytes, never a database refit."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from app.analytics.stop_availability.models import EvidenceModel, SnapshotIdentity

NORMALIZATION_VERSION = "stop-availability-krasnoyarsk-relative-v1"
SAMPLING_VERSION = "district-territorial-grid250-v1"
REFERENCE_ID = "research-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-center-cdf-v1"
REFERENCE_PATH = Path(__file__).resolve().parents[3] / "data/fixtures/analytics/stop-availability-krasnoyarsk-relative-v1.json"
# Whole-file SHA256 is pinned outside the artifact (no self-referential digest).
REFERENCE_SHA256 = "8a0ac0adfde9d4f1f3f33d630bb8bcab0a64d81cd9d7e1a5580343c441452cb5"
DISTANCES_SHA256 = "e4c08d4d7d63d83f56343db867f9285ccfc4ac0ccfa50cbf2eb703dfdca7d535"


class DistrictReference(EvidenceModel):
    slug: str
    geometry_ewkb_md5: str = Field(pattern=r"^[0-9a-f]{32}$")
    sample_count: int = Field(ge=180)


class ReferenceContract(EvidenceModel):
    contract_version: Literal["stop-availability-calibration-reference-v1"]
    normalization_version: Literal["stop-availability-krasnoyarsk-relative-v1"]
    reference_id: Literal["research-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-center-cdf-v1"]
    reference_city: Literal["Krasnoyarsk"]
    scope_id: Literal["krasnoyarsk"]
    evidence_version: Literal["stop-availability-evidence-v1"]
    eligibility_version: Literal["osm-highway-bus-stop-v1"]
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"]
    sampling_version: Literal["district-territorial-grid250-v1"]
    cdf_method: Literal["empirical-midrank-no-interpolation-v1"]
    sample_count: Literal[6065]
    distances_sha256: Literal["e4c08d4d7d63d83f56343db867f9285ccfc4ac0ccfa50cbf2eb703dfdca7d535"]
    distances_m: tuple[float, ...]
    osm_snapshot: SnapshotIdentity
    geometry_fixture_sha256: Literal["7ac78515978087c0ba0272eaa427731473ee63421019eb962aa7e449c18e37a2"]
    districts: tuple[DistrictReference, ...]
    research_reference_artifact_sha256: Literal["c4ce0878b39fd8e123ab2121e313709f0ffbc6084a340ef477573a8c5a9679c9"]
    research_point_evidence_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
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
