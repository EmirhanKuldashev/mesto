"""Pure equal-weight composition. No source queries, normalization or fallback."""
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import Field

from app.analytics.stop_availability.models import EvidenceModel

CALCULATION_VERSION = "objective-mesto-v2"
WEIGHTS = MappingProxyType(dict.fromkeys(
    ("stop_availability", "school", "kindergarten", "healthcare", "parks"), 0.20))


class ComponentScore(EvidenceModel):
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    normalization_version: str
    sampling_version: str
    evidence_version: str
    eligibility_version: str
    reference_id: str
    reference_checksum: str
    unavailable_reason: str | None = None
    limitations: tuple[str, ...] = ()
    provenance: dict = Field(default_factory=dict)


class ObjectiveScore(EvidenceModel):
    calculation_version: Literal["objective-mesto-v2"] = CALCULATION_VERSION
    score: float | None
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    coverage: float
    components: dict[str, ComponentScore]
    weights: dict[str, float] = Field(default_factory=lambda: dict(WEIGHTS))
    unavailable_reason: str | None
    limitations: tuple[str, ...]
    provenance: dict = Field(default_factory=dict)


def aggregate(components: Mapping[str, ComponentScore], *, provenance: dict | None = None) -> ObjectiveScore:
    if set(components) - WEIGHTS.keys():
        raise ValueError("Only the five canonical objective components are accepted")
    missing = [name for name in WEIGHTS if name not in components or
               components[name].score is None or components[name].unavailable_reason]
    reason = "; ".join(f"{name}:{components[name].unavailable_reason or 'score_unavailable'}"
                       if name in components else f"{name}:component_missing" for name in missing) or None
    # Fixed iteration order, exactly one rounding of the final composite.
    score = None if missing else round(sum(WEIGHTS[n] * components[n].score for n in WEIGHTS), 2)
    limits = {"balanced_territorial_not_personal_or_population_weighted",
              "relative_to_frozen_krasnoyarsk_reference_not_universal"}
    limits.update(limit for c in components.values() for limit in c.limitations)
    return ObjectiveScore(score=score, availability="UNAVAILABLE" if missing else "AVAILABLE",
        coverage=(5 - len(missing)) / 5, components=dict(components), unavailable_reason=reason,
        limitations=tuple(sorted(limits)), provenance=provenance or {})
