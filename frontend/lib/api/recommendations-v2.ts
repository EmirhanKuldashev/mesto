import type { LocalLocation } from '@/types/local';
import type { MatchProfile, MatchResponse } from '@/types/recommendations-v2';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v==='object' && !Array.isArray(v);
const score = (v: unknown) => v===null || typeof v==='number' && Number.isFinite(v) && v>=0 && v<=100;
const finite = (v:unknown) => v===null || typeof v==='number' && Number.isFinite(v) && v>=0;
const strings = (v:unknown) => Array.isArray(v) && v.every(s=>typeof s==='string');
const nullableText = (v:unknown) => v===null || typeof v==='string';
const metric = (v:unknown) => finite(v) || typeof v==='string' && v.trim()!=='' && Number.isFinite(Number(v)) && Number(v)>=0;
const localValid = (v:unknown) => v===null || record(v) && score(v.score) && record(v.components) && Object.values(v.components).every(c=>record(c) && score(c.score) && finite(c.distance_m));
const domainsValid = (v:unknown) => record(v) && ['infrastructure','mobility','affordability'].every(k => {
  const d=v[k];if(!record(d) || !score(d.score) || !score(d.contribution) || !finite(d.weight) || typeof d.weight==='number' && d.weight>1 || !record(d.evidence))return false;
  if(!nullableText(d.reason))return false;
  if(k==='infrastructure')return Array.isArray(d.evidence.contributions) && d.evidence.contributions.every(c=>record(c) &&
    typeof c.component==='string' && score(c.utility) && finite(c.importance) && finite(c.normalized_weight) && score(c.contribution));
  if(k!=='mobility')return true;
  return Array.isArray(d.evidence.trips) && d.evidence.trips.every(e=>record(e) && record(e.trip) && typeof e.trip.label==='string' &&
    finite(e.minutes) && score(e.utility) && finite(e.trip.comfortable_minutes) && finite(e.trip.soft_limit_minutes) && finite(e.trip.importance) && finite(e.trip.visits_per_week));
});
export function validMatchResponse(v: unknown): v is MatchResponse {
  if (!record(v) || v.version!=='match-recommendations-v2' || !record(v.profile) || v.profile.version!=='personal-match-v2' ||
    !record(v.sample) || v.sample.complete_apartment_market!==false || !Array.isArray(v.candidates) || !Array.isArray(v.districts) || !Array.isArray(v.limitations)) return false;
  return v.sample.count===v.candidates.length && v.candidates.every(c => record(c) && typeof c.name==='string' && score(c.score) &&
    nullableText(c.score_reason) && finite(c.coverage) && typeof c.coverage==='number' && c.coverage<=1 &&
    ['PASS','FAIL','UNKNOWN'].includes(String(c.eligibility)) && ['verified','unknown','failed'].includes(String(c.bucket)) &&
    (c.bucket!=='verified' || c.eligibility==='PASS' && c.score!==null) && (c.eligibility!=='FAIL' || c.bucket==='failed') &&
    domainsValid(c.domains) &&
    localValid(c.objective_local) && (c.objective_district===null || record(c.objective_district) && score(c.objective_district.score)) &&
    record(c.source) && (c.price_from===null || typeof c.price_from==='string' && Number.isFinite(Number(c.price_from))) &&
    Array.isArray(c.constraints) && c.constraints.every(check => record(check) && typeof check.key==='string' && metric(check.actual) && metric(check.limit) && nullableText(check.reason) && ['PASS','FAIL','UNKNOWN'].includes(String(check.status))) &&
    strings(c.limitations) && strings(c.explanations)) && v.districts.every(d => record(d) && typeof d.district_id==='number' && typeof d.district_name==='string' && score(d.best_observed_match) &&
      ['observed_count','evaluated_count','verified_count','unknown_count','failed_count'].every(k=>Number.isInteger(d[k]) && Number(d[k])>=0));
}
export async function recommendationsV2(profile:MatchProfile,signal:AbortSignal,point?:LocalLocation):Promise<MatchResponse> {
  const response=await fetch(`${API_URL}/api/recommendations/v2`,{ method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile,...(point ? {point} : {})}),signal,cache:'no-store' });
  if(!response.ok) throw new Error(`Не удалось рассчитать Match (HTTP ${response.status}). Проверьте настройки и пределы.`);
  const value:unknown=await response.json();
  if(!validMatchResponse(value)) throw new Error('Сервер вернул некорректную схему Match V2');
  return value;
}
