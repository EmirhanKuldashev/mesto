"""Offline, explicit packaged baseline selection through the existing lifecycle."""
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from sqlalchemy import func, select

from app import models
from data.osm.contracts import BuildResult, Contract, Manifest, Observation, Quality, canonical_bytes, checksum
from data.osm.lifecycle import activate_snapshot, persist_candidate, review_for_activation

CURRENT_BASELINE = Path(__file__).resolve().parents[1] / "fixtures/osm/current-baseline.json"
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PackagedReview(Contract):
    policy: Literal["osm-proxy-reviewed-unknown-v1"]
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PreviousBaseline(Contract):
    kind: Literal["legacy"]
    fixture: str
    fixture_checksum: Sha256
    observation_count: int = Field(gt=0)


class BaselineContract(Contract):
    contract_version: Literal["osm-packaged-baseline-v1"]
    source_id: Literal["osm"]
    scope_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    bundle: str
    canonical_checksum: Sha256
    compressed_checksum: Sha256
    manifest_checksum: Sha256
    build_report_checksum: Sha256
    raw_response_checksum: Sha256
    query_version: str
    query_hash: Sha256
    observation_count: int = Field(gt=0)
    eligible_count: int = Field(gt=0)
    category_counts: dict[str, int]
    unnamed_counts: dict[str, int]
    activation_review: PackagedReview
    clean_history_policy: Literal["fresh_initial"]
    previous_baseline: PreviousBaseline


def read_packaged_baseline(contract_path: Path = CURRENT_BASELINE):
    """Verify exact accepted bytes; no raw store, collection, rebuild or new source time."""
    contract_path = Path(contract_path)
    contract = BaselineContract.model_validate_json(contract_path.read_bytes())
    root = contract_path.parent.resolve()
    bundle = (root / contract.bundle).resolve()
    if not bundle.is_relative_to(root):
        raise ValueError("Packaged baseline path escapes fixture root")

    def verified(name, expected):
        data = (bundle / name).read_bytes()
        if checksum(data) != expected:
            raise ValueError("Packaged baseline checksum mismatch: " + name)
        return data

    compressed = verified("canonical.json.gz", contract.compressed_checksum)
    raw = gzip.decompress(compressed)
    if checksum(raw) != contract.canonical_checksum:
        raise ValueError("Packaged canonical checksum mismatch")
    manifest = Manifest.model_validate_json(verified("manifest.json", contract.manifest_checksum))
    report = json.loads(verified("build-report.json", contract.build_report_checksum))
    canonical = json.loads(raw)
    observations = tuple(Observation.model_validate(row) for row in canonical["observations"])
    quality = Quality.model_validate(canonical["quality"])
    for key in ("source_id", "scope_id", "snapshot_id", "query_version", "query_hash"):
        if canonical[key] != getattr(contract, key) or getattr(manifest, key) != getattr(contract, key):
            raise ValueError("Packaged baseline version/identity mismatch: " + key)
    if (canonical_bytes(canonical) != raw or manifest.known_limitations or
        len(manifest.parts) != 1 or manifest.parts[0].artifact_checksum != contract.raw_response_checksum):
        raise ValueError("Packaged canonical/manifest evidence mismatch")
    if (len(observations) != contract.observation_count or
        sum(row.eligible for row in observations) != contract.eligible_count or
        len({row.identity for row in observations}) != len(observations) or
        any((row.dataset_id, row.scope_id, row.snapshot_id) !=
            (manifest.dataset_id, manifest.scope_id, manifest.snapshot_id) for row in observations)):
        raise ValueError("Packaged baseline membership mismatch")
    if (report["observation_count"] != contract.observation_count or
        report["eligible_count"] != contract.eligible_count or report["duplicate_count"] or
        report["conflicts"] or report["part_errors"] or report["exclusions"] or
        report["quality"] != quality.model_dump(mode="json") or
        report["canonical_checksum"] != contract.canonical_checksum):
        raise ValueError("Packaged build report mismatch")
    if (dict(Counter(row.category for row in observations if row.eligible)) != contract.category_counts or
        dict(Counter(row.category for row in observations if row.eligible and row.name is None)) != contract.unnamed_counts):
        raise ValueError("Packaged category/name counts mismatch")
    return contract, manifest, BuildResult(canonical=canonical, canonical_checksum=contract.canonical_checksum,
        observations=observations, quality=quality, report=report)


def load_current_baseline(session, contract_path: Path = CURRENT_BASELINE):
    """Clean DB starts fresh; an upgraded DB keeps history and unchanged active payload."""
    contract, manifest, result = read_packaged_baseline(contract_path)
    with session.begin_nested():
        dataset = session.scalar(select(models.OsmDataset).where(
            models.OsmDataset.source_id == contract.source_id, models.OsmDataset.scope_id == contract.scope_id
        ).with_for_update().execution_options(populate_existing=True))
        active = session.get(models.OsmSnapshot, dataset.active_snapshot_id) if dataset and dataset.active_snapshot_id else None
        if active is not None and not active.is_legacy and active.version != contract.snapshot_id:
            raise ValueError("Existing active OSM version differs: explicit baseline review required")
        # persist_candidate serializes simultaneous clean bootstraps on source/scope.
        snapshot = persist_candidate(session, result, manifest=manifest)
        dataset = session.get(models.OsmDataset, snapshot.dataset_id, populate_existing=True)
        if snapshot.status == "ACTIVE":
            if dataset.active_snapshot_id != snapshot.id:
                raise ValueError("Packaged baseline active pointer mismatch")
            state = "unchanged"
        else:
            if snapshot.status == "CANDIDATE":
                review_for_activation(session, snapshot.id, reviewer=contract.activation_review.reviewer,
                                      reason=contract.activation_review.reason)
            if snapshot.status != "VALIDATED":
                raise ValueError("Packaged baseline cannot be reactivated from " + snapshot.status)
            activate_snapshot(session, snapshot.id)
            state = "activated"
        count = session.scalar(select(func.count()).select_from(models.OsmActivePoi).where(
            models.OsmActivePoi.dataset_id == dataset.id, models.OsmActivePoi.snapshot_id == snapshot.id))
        if count != contract.eligible_count:
            raise ValueError("Packaged baseline active membership mismatch")
        return {"snapshot": snapshot.version, "snapshot_id": snapshot.id, "state": state,
                "total": count, "canonical_checksum": snapshot.canonical_checksum}


def main():
    from app.db import create_session_factory
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            print(load_current_baseline(session))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
