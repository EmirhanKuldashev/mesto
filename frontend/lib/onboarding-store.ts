import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Coordinates = { latitude: number; longitude: number };
export type LifePoint = Coordinates & {
  localId: string;
  owner_type: "primary_user" | "partner";
  type: "work" | "partner_work" | "school" | "kindergarten" | "parents" | "university" | "other";
  name: string;
  importance: number;
  frequency_per_week: number;
};

export const weightNames = [
  "education_weight", "kindergarten_weight", "healthcare_weight", "transport_weight",
  "ecology_weight", "safety_weight", "parks_weight", "shopping_weight",
  "entertainment_weight", "housing_price_weight", "future_growth_weight",
] as const;
export type WeightName = (typeof weightNames)[number];
export type PreferenceName = WeightName | "quiet_active" | "green_urban" | "center_calm" | "price_vs_time" | "today_vs_future" | "car_dependency";
export type PreferenceValue = { value: number | null; is_answered: boolean; source: "user" | "partner" | "default"; confidence: number };
export type Preferences = Record<PreferenceName, PreferenceValue>;
export const unansweredPreference = (): PreferenceValue => ({ value: null, is_answered: false, source: "default", confidence: 0 });
export const answeredPreference = (value: number, source: "user" | "partner"): PreferenceValue => ({ value, is_answered: true, source, confidence: 1 });

export type OnboardingDraft = {
  name: string;
  household_type: "single" | "couple" | "family" | "family_with_relatives";
  adults_count: number;
  children: { age: number }[];
  housing_goal: "buy" | "rent" | "compare";
  commute_minutes: number | null;
  purchase_budget: number;
  initial_payment: number;
  comfortable_monthly_payment: number;
  rent_budget: number;
  planning_horizon: "1_2_years" | "3_5_years" | "5_10_years" | "long_term";
  car_availability: boolean;
  transport_preferences: ("car" | "public_transport" | "walking" | "bicycle")[];
  preferences: Preferences;
  future_changes: ("child" | "new_job" | "no_car" | "bigger_family" | "relocation" | "longer_horizon")[];
  home_values: ("family_time" | "calm" | "financial_stability" | "mobility" | "green_environment" | "district_growth" | "nearby_infrastructure" | "personal_space")[];
  good_home_text: string;
  partner: { name: string; work_point: Coordinates | null; transport_preferences: OnboardingDraft["transport_preferences"]; preferences: Partial<Preferences>; life_goals: string[] };
  life_points: LifePoint[];
  data_processing_consent: boolean;
};

const preferences = Object.fromEntries([...weightNames, "quiet_active", "green_urban", "center_calm", "price_vs_time", "today_vs_future", "car_dependency"].map((key) => [key, unansweredPreference()])) as Preferences;

export const initialDraft: OnboardingDraft = {
  name: "", household_type: "single", adults_count: 1, children: [], housing_goal: "compare",
  commute_minutes: null, purchase_budget: 0, initial_payment: 0, comfortable_monthly_payment: 0, rent_budget: 0,
  planning_horizon: "3_5_years", car_availability: false,
  transport_preferences: ["public_transport"], preferences,
  future_changes: [],
  home_values: [], good_home_text: "", data_processing_consent: false,
  partner: { name: "", work_point: null, transport_preferences: ["public_transport"], preferences: {}, life_goals: [] },
  life_points: [],
};

type State = {
  step: number;
  draft: OnboardingDraft;
  profileId: string | null;
  setStep: (step: number) => void;
  patch: (patch: Partial<OnboardingDraft>) => void;
  setPreference: (name: PreferenceName, value: number | null) => void;
  upsertPoint: (point: LifePoint) => void;
  removePoint: (localId: string) => void;
  setProfileId: (id: string) => void;
  reset: () => void;
};

export const useOnboarding = create<State>()(persist((set) => ({
  step: 0, draft: initialDraft, profileId: null,
  setStep: (step) => set({ step: Math.max(0, Math.min(9, step)) }),
  patch: (patch) => set((state) => ({ draft: { ...state.draft, ...patch }, profileId: null })),
  setPreference: (name, value) => set((state) => ({ draft: { ...state.draft,
    preferences: { ...state.draft.preferences, [name]: value === null ? unansweredPreference() : answeredPreference(value, "user") } }, profileId: null })),
  upsertPoint: (point) => set((state) => ({ draft: { ...state.draft,
    life_points: [...state.draft.life_points.filter((item) => item.localId !== point.localId), point] }, profileId: null })),
  removePoint: (localId) => set((state) => ({ draft: { ...state.draft,
    life_points: state.draft.life_points.filter((point) => point.localId !== localId) }, profileId: null })),
  setProfileId: (profileId) => set({ profileId }),
  reset: () => set({ draft: initialDraft, step: 0, profileId: null }),
}), { name: "mesto-onboarding-v2", storage: createJSONStorage(() => localStorage),
  version: 1,
  migrate: (persisted) => {
    const state = persisted as { step?: number; draft?: OnboardingDraft; profileId?: string | null };
    if (state.draft?.life_points?.some((point) => point.localId.startsWith("demo-")))
      return { step: 0, draft: initialDraft, profileId: null };
    return persisted as State;
  },
  partialize: ({ step, draft, profileId }) => ({ step, draft, profileId }) }));
