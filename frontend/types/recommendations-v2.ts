import type { LocalLocation } from './local';

export type Priority = 0 | 1 | 2 | 3 | null;
export type InfraKey = 'stop' | 'school' | 'kindergarten' | 'healthcare' | 'parks';
export type TripSettings = { importance: Priority; visits_per_week: number | null; comfortable_minutes: number | null; soft_limit_minutes: number | null; hard_limit_minutes: number | null };
export type MatchSettings = {
  infrastructure: Record<InfraKey, Priority>;
  domains: Record<'infrastructure' | 'mobility' | 'affordability', Priority>;
  max_distance_m: Record<string, number>;
  mode: 'car' | 'public_transport' | null;
  trips: Record<string, TripSettings>;
  comfortable_price: number | null;
  frequency_weighting_confirmed: boolean;
};
export type MatchProfile = {
  version: 'personal-match-v2'; housing_goal: 'buy' | 'rent' | 'compare';
  weights: Record<'infrastructure' | 'mobility' | 'affordability', number | null>;
  infrastructure: Record<InfraKey, Priority>; max_distance_m: Record<string, number>;
  mode: 'car' | 'public_transport' | null; frequency_weighting_confirmed: boolean;
  trips: (TripSettings & LocalLocation & { label: string; kind: 'work' | 'university' | 'school' | 'relatives' | 'other' })[];
  maximum_budget: number | null; comfortable_price: number | null;
};
export type MatchCandidate = {
  id: number | null; name: string; district_id: number | null; district_name: string | null;
  location: LocalLocation | null; price_from: string | null; source: Record<string, unknown>;
  score: number | null; score_reason: string | null; coverage: number;
  eligibility: 'PASS' | 'FAIL' | 'UNKNOWN'; bucket: 'verified' | 'unknown' | 'failed';
  domains: Record<string, { score: number | null; weight: number | null; contribution: number | null; reason: string | null; evidence: Record<string, unknown> }>;
  constraints: { key: string; status: 'PASS' | 'FAIL' | 'UNKNOWN'; actual: number | string | null; limit: number | string | null; reason: string | null }[];
  objective_local: { score: number | null; availability: string; components: Record<string, { score: number | null; distance_m: number | null }> } | null;
  objective_district: { score: number | null; availability: string } | null;
  limitations: string[]; explanations: string[];
};
export type MatchResponse = {
  version: 'match-recommendations-v2'; profile: Omit<MatchProfile,'maximum_budget'|'comfortable_price'> & { maximum_budget:string|null; comfortable_price:string|null };
  sample: { count: number; kind: string; complete_apartment_market: false; candidate_ids: (number | null)[]; unassigned_count: number };
  candidates: MatchCandidate[];
  districts: { district_id: number; district_name: string; observed_count: number; evaluated_count: number; verified_count: number; unknown_count: number; failed_count: number; best_candidate_id: number | null; best_observed_match: number | null }[];
  limitations: string[];
};
