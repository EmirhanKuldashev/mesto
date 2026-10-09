"""Pure utilities and eligibility. No database, routing or objective bonus."""
import math
from .v2_models import Constraint, Domain


def decreasing_utility(actual, comfortable, soft_limit):
    if actual is None or comfortable is None or soft_limit is None:
        return None
    if not all(math.isfinite(float(v)) for v in (actual, comfortable, soft_limit)) or actual < 0 or comfortable < 0 or soft_limit <= comfortable:
        raise ValueError('Finite, ordered utility anchors required')
    if actual <= comfortable:
        return 100.0
    if actual >= soft_limit:
        return 0.0
    return float(100 * (soft_limit - actual) / (soft_limit - comfortable))


def constraint(key, actual, limit, reason=None):
    return Constraint(key=key, actual=actual, limit=limit,
        status='UNKNOWN' if actual is None or limit is None else 'PASS' if actual <= limit else 'FAIL', reason=reason)


def eligibility(checks):
    return 'FAIL' if any(c.status == 'FAIL' for c in checks) else 'UNKNOWN' if any(c.status == 'UNKNOWN' for c in checks) else 'PASS'


def compose(values, weights):
    domains = {}
    for key, (score, reason, evidence) in values.items():
        weight = getattr(weights, key)
        domains[key] = Domain(score=score, weight=weight,
            contribution=0.0 if weight == 0 else weight * score if weight is not None and score is not None else None,
            reason=reason, evidence=evidence)
    if any(d.weight is None for d in domains.values()):
        return domains, None, 'domain_weights_missing', 0.0
    active = [d for d in domains.values() if d.weight > 0]
    if not active:
        return domains, None, 'all_domains_excluded', 0.0
    coverage = min(1.0, math.fsum(d.weight for d in active if d.score is not None))
    if any(d.score is None for d in active):
        return domains, None, 'active_domain_unavailable', coverage
    return domains, min(100.0, math.fsum(d.contribution for d in active)), None, coverage
