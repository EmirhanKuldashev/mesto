import { isLocalResult } from './local';
import { isMobilityResult } from './mobility';
import { localKeys } from '@/types/local';
import type { MatchRequest, MatchResult } from '@/types/match-v2';

const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const nullableNumber = (v: unknown) => v === null || finite(v);
const score = (v: unknown) => finite(v) && v >= 0 && v <= 100;
const statuses = ['AVAILABLE','UNAVAILABLE','NOT_CALCULATED','NOT_APPLICABLE'];

export function isMatchResult(v: unknown, request: MatchRequest): v is MatchResult {
  if (!record(v) || v.version !== 'match-v2-foundation-v1' || v.research_gate !== 'B' || v.overall_match !== null ||
      !record(v.candidate) || v.candidate.latitude !== request.candidate.latitude || v.candidate.longitude !== request.candidate.longitude ||
      !record(v.objective) || !isLocalResult(v.objective.mesto_local) ||
      v.objective.mesto_local.location.latitude !== request.candidate.latitude || v.objective.mesto_local.location.longitude !== request.candidate.longitude ||
      !record(v.personal_fit) || !record(v.personal_fit.housing) || v.personal_fit.housing.availability !== 'NOT_IMPLEMENTED' ||
      !Array.isArray(v.limitations) || !v.limitations.every(s => typeof s === 'string')) return false;
  const fit = v.personal_fit.infrastructure, mobility = v.personal_fit.mobility, affordability = v.personal_fit.affordability;
  if (!record(fit) || !statuses.includes(String(fit.availability)) ||
      (fit.availability === 'AVAILABLE' ? !score(fit.score) : fit.score !== null) ||
      !Array.isArray(fit.contributions) || fit.contributions.length !== 5 || !record(mobility) ||
      !statuses.includes(String(mobility.availability)) || !Array.isArray(mobility.destinations) ||
      mobility.destinations.length !== (request.profile.mobility?.destinations.length ?? 0)) return false;
  const local = v.objective.mesto_local;
  const priorities = Object.values(request.profile.infrastructure);
  const complete = priorities.every(p => p !== null);
  const total = priorities.reduce<number>((sum, p) => sum + (p ?? 0), 0);
  const missingRequired = localKeys.some(k => (request.profile.infrastructure[k === 'stop_availability' ? 'stop' : k] ?? 0) > 0 && !local.components[k].available);
  const expectedAvailability = !complete || !total ? 'NOT_CALCULATED' : missingRequired ? 'UNAVAILABLE' : 'AVAILABLE';
  if (fit.availability !== expectedAvailability || fit.version !== 'infrastructure-fit-experimental-v1') return false;
  if (!fit.contributions.every((c, i) => {
    const key = localKeys[i], importance = request.profile.infrastructure[key === 'stop_availability' ? 'stop' : key];
    const normalized = complete && total ? importance! / total : null;
    const contribution = normalized === null ? null : importance === 0 ? 0 : local.components[key].available ? normalized * local.components[key].score! : null;
    return record(c) && c.component === key && c.utility === local.components[key].score && c.importance === importance &&
      c.availability === (local.components[key].available ? 'AVAILABLE' : 'UNAVAILABLE') && record(c.provenance) &&
      c.normalized_weight === normalized && c.contribution === contribution;
  })) return false;
  if (fit.availability === 'AVAILABLE' && Math.abs(fit.contributions.reduce((s, c) => s + (c as { contribution: number }).contribution, 0) - (fit.score as number)) > 1e-10) return false;
  if (!mobility.destinations.every((d, i) => {
    const expected = request.profile.mobility!.destinations[i];
    if (!record(d) || !record(d.destination) || d.mode !== request.profile.mobility!.preferred_mode ||
        !Object.entries(expected).every(([k, value]) => d.destination && (d.destination as Record<string, unknown>)[k] === value) ||
        !statuses.includes(String(d.availability)) || !(d.within_threshold === null || typeof d.within_threshold === 'boolean') || !nullableNumber(d.delta_minutes)) return false;
    if (d.route === null) return d.availability === 'NOT_CALCULATED' && d.within_threshold === null && d.delta_minutes === null;
    if (!d.mode || !isMobilityResult(d.route, { origin: request.candidate, destination: expected, mode: d.mode as 'car' | 'public_transport' })) return false;
    const delta = d.route.availability === 'AVAILABLE' && expected.max_acceptable_minutes !== null ? d.route.duration_seconds! / 60 - expected.max_acceptable_minutes : null;
    return d.availability === d.route.availability && d.delta_minutes === delta && d.within_threshold === (delta === null ? null : delta <= 0);
  })) return false;
  const money = (m: unknown) => m === null || typeof m === 'string' && Number.isFinite(Number(m));
  return record(affordability) && statuses.includes(String(affordability.availability)) &&
    [affordability.observed_price_from, affordability.purchase_budget, affordability.budget_delta].every(money) &&
    (affordability.purchase_budget === null ? request.profile.purchase_budget === null : Number(affordability.purchase_budget) === request.profile.purchase_budget) &&
    (affordability.availability === 'AVAILABLE' ? request.market_candidate_id !== null && affordability.source === 'cian' &&
      affordability.observed_price_from !== null && typeof affordability.within_budget === 'boolean' && affordability.budget_delta !== null :
      affordability.within_budget === null && affordability.budget_delta === null);
}

export async function calculateMatch(request: MatchRequest, signal: AbortSignal): Promise<MatchResult> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/analytics/match-v2`, {
    method: 'POST', cache: 'no-store', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Не удалось проверить предпочтения (HTTP ${response.status})`);
  const payload: unknown = await response.json();
  if (!isMatchResult(payload, request)) throw new Error('Получен некорректный результат проверки предпочтений');
  return payload;
}
