"""Approved District territorial grid; separate from coordinate normalization."""
import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.analytics.kindergarten.models import Coordinate
from app.analytics.kindergarten.reference import LoadedReference, SAMPLING_VERSION
from app.analytics.stop_availability.sampling import GRID_250_QUERY

MINIMUM_VALID_SAMPLES = 180  # Lower edge of validated District domain, not a population law.

@dataclass(frozen=True)
class TerritorialSample:
    cell_x: int
    cell_y: int
    coordinate: Coordinate


@dataclass(frozen=True)
class DistrictSampling:
    district_id: int
    samples: tuple[TerritorialSample, ...] = ()
    sampling_version: str = SAMPLING_VERSION
    unavailable_reason: str | None = None


def district_grid_250(session: Session, district_ids: Sequence[int], *,
                      reference: LoadedReference) -> tuple[DistrictSampling, ...]:
    """One SQL query, fixed centers, original polygon ST_Covers; no POI lookup."""
    ids = tuple(sorted(set(district_ids)))
    if not ids or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Supply positive District IDs")
    payload = [d.model_dump() for d in reference.contract.districts]
    groups = {}
    for row in session.execute(GRID_250_QUERY, {
            "district_ids": list(ids), "district_reference": json.dumps(payload)}).mappings():
        groups.setdefault(row["id"], []).append(row)
    results = []
    for ident in ids:
        rows = groups.get(ident, [])
        reason = None
        if not rows or not rows[0]["geometry_valid"]:
            reason = "sampling_unavailable"
        elif not rows[0]["domain_valid"]:
            reason = "sampling_domain_unvalidated"
        samples = tuple(TerritorialSample(row["x"], row["y"],
            Coordinate(longitude=row["longitude"], latitude=row["latitude"]))
            for row in rows if row["x"] is not None) if reason is None else ()
        if reason is None and len(samples) < MINIMUM_VALID_SAMPLES:
            reason = "insufficient_samples"
        elif reason is None and len(samples) != rows[0]["expected_count"]:
            reason = "sampling_contract_mismatch"
        results.append(DistrictSampling(ident, samples, unavailable_reason=reason))
    return tuple(results)
