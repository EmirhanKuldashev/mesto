"""School territorial grid250 RESEARCH consumer, with no approved School sampler."""
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from sqlalchemy.orm import Session

from app.analytics.school.aggregation import summarize
from app.analytics.school.models import EvidenceModel, SchoolAvailabilitySummary, SchoolPointDiagnostics
from app.analytics.school.service import SchoolAvailabilityService
from app.analytics.stop_availability.reference import read_reference
from app.analytics.stop_availability.sampling import district_grid_250

SAMPLING_VERSION = "school-research-territorial-grid250-v1"


class SchoolResearchDistrict(EvidenceModel):
    purpose: Literal["RESEARCH_USE_FOR_SCHOOL"] = "RESEARCH_USE_FOR_SCHOOL"
    district_id: int
    summary: SchoolAvailabilitySummary
    diagnostics: tuple[SchoolPointDiagnostics, ...]


def district_research(session: Session, district_ids: Sequence[int], *, scope_id: str) -> tuple[SchoolResearchDistrict, ...]:
    """Two queries: existing geometry-validated grid and one School d1/d2/d3 batch.

    Stop's reference is used ONLY for accepted polygon/grid identity checks, never
    for its CDF/distances or School normalization. School sampling remains research.
    """
    if scope_id != "krasnoyarsk":
        raise ValueError("This research grid is validated only for Krasnoyarsk polygons")
    grids = district_grid_250(session,district_ids,reference=read_reference())
    if any(g.unavailable_reason for g in grids):
        raise ValueError("School research sampling unavailable or outside reviewed polygon domain")
    samples = [(g.district_id,s.coordinate) for g in grids for s in g.samples]
    diagnostics = SchoolAvailabilityService(session,scope_id=scope_id).diagnostics([c for _,c in samples])
    groups = defaultdict(list)
    for (ident,_),result in zip(samples,diagnostics,strict=True):
        groups[ident].append(result)
    return tuple(SchoolResearchDistrict(district_id=g.district_id,
        summary=summarize([d.evidence for d in groups[g.district_id]],sampling_version=SAMPLING_VERSION,
                          radii_m=(500,1000,1500)),diagnostics=tuple(groups[g.district_id])) for g in grids)
