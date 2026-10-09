import type { OnboardingDraft } from './onboarding-store';
import type { MatchProfile, MatchSettings, TripSettings } from '@/types/recommendations-v2';

export const emptyTrip = (): TripSettings => ({ importance:null,visits_per_week:null,comfortable_minutes:null,soft_limit_minutes:null,hard_limit_minutes:null });
export const emptyMatchSettings = (): MatchSettings => ({
  infrastructure:{ stop:null,school:null,kindergarten:null,healthcare:null,parks:null },
  domains:{ infrastructure:null,mobility:null,affordability:null },max_distance_m:{},mode:null,trips:{},comfortable_price:null,frequency_weighting_confirmed:false,
});
export function matchProfile(draft: OnboardingDraft): MatchProfile {
  const settings = draft.match_v2 ?? emptyMatchSettings();
  const values = Object.values(settings.domains);
  const total = values.reduce<number>((sum,v) => sum+(v ?? 0),0);
  const weights = Object.fromEntries(Object.entries(settings.domains).map(([k,v]) => [k,v===null ? null : total ? v/total : 0])) as MatchProfile['weights'];
  return { version:'personal-match-v2',housing_goal:draft.housing_goal,weights,infrastructure:settings.infrastructure,
    max_distance_m:settings.max_distance_m,mode:settings.mode,frequency_weighting_confirmed:settings.frequency_weighting_confirmed,
    maximum_budget:draft.purchase_budget>0 ? draft.purchase_budget : null,comfortable_price:settings.comfortable_price,
    trips:draft.life_points.map(p => ({ ...(settings.trips[p.localId] ?? emptyTrip()),latitude:p.latitude,longitude:p.longitude,label:p.name,
      kind:p.type==='work'||p.type==='partner_work' ? 'work' : p.type==='school' ? 'school' : p.type==='university' ? 'university' : p.type==='parents' ? 'relatives' : 'other' })),
  };
}
