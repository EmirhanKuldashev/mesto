import type { LocalKey, LocalLocation, LocalResult } from './local';
import type { MobilityResult, PersonalDestination, TravelMode } from './mobility';

export type Importance = 0 | 1 | 2 | 3;
export type InfrastructureImportance = Record<'stop' | 'school' | 'kindergarten' | 'healthcare' | 'parks', Importance | null>;
export type MatchDestination = PersonalDestination & { importance: Importance; max_acceptable_minutes: number | null };
export type MatchRequest = { candidate: LocalLocation; profile: {
  infrastructure: InfrastructureImportance;
  mobility: { preferred_mode: TravelMode | null; destinations: MatchDestination[] } | null;
  purchase_budget: number | null;
}; market_candidate_id: number | null };
export type MatchResult = {
  version: 'match-v2-foundation-v1'; research_gate: 'B'; candidate: LocalLocation;
  objective: { mesto_local: LocalResult }; overall_match: null; limitations: string[];
  personal_fit: {
    infrastructure: { availability: string; score: number | null; unavailable_reason: string | null;
      contributions: { component: LocalKey; utility: number | null; importance: Importance | null;
        normalized_weight: number | null; contribution: number | null; availability: string; provenance: Record<string, unknown> }[] };
    mobility: { availability: string; destinations: { destination: MatchDestination; mode: TravelMode | null;
      availability: string; route: MobilityResult | null; within_threshold: boolean | null; delta_minutes: number | null }[] };
    affordability: { availability: string; observed_price_from: string | null; purchase_budget: string | null;
      within_budget: boolean | null; budget_delta: string | null; source: string | null; fetched_at: string | null };
    housing: { availability: 'NOT_IMPLEMENTED' };
  };
};
