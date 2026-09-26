import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Coordinates = { latitude: number; longitude: number };
export type LifePoint = Coordinates & {
  localId: string;
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
export type PreferenceName = WeightName | "quiet_active" | "green_urban" | "center_calm";
export type Preferences = Record<PreferenceName, number>;

export type OnboardingDraft = {
  name: string;
  household_type: "single" | "couple" | "family" | "family_with_relatives";
  adults_count: number;
  children: { age: number }[];
  housing_goal: "buy" | "rent" | "compare";
  purchase_budget: number;
  initial_payment: number;
  comfortable_monthly_payment: number;
  rent_budget: number;
  planning_horizon: "1_2_years" | "3_5_years" | "5_10_years" | "long_term";
  car_availability: boolean;
  transport_preferences: ("car" | "public_transport" | "walking" | "bicycle")[];
  preferences: Preferences;
  price_vs_time: number;
  today_vs_future: number;
  car_dependency: number;
  future_changes: ("child" | "new_job" | "no_car" | "bigger_family" | "relocation" | "longer_horizon")[];
  home_values: ("family_time" | "calm" | "financial_stability" | "mobility" | "green_environment" | "district_growth" | "nearby_infrastructure" | "personal_space")[];
  good_home_text: string;
  partner: { name: string; work_point: Coordinates | null; transport_preferences: OnboardingDraft["transport_preferences"]; preferences: Record<string, number>; life_goals: string[] };
  life_points: LifePoint[];
  data_processing_consent: boolean;
};

const preferences = Object.fromEntries([...weightNames, "quiet_active", "green_urban", "center_calm"].map((key) => [key, 50])) as Preferences;

export const initialDraft: OnboardingDraft = {
  name: "", household_type: "single", adults_count: 1, children: [], housing_goal: "compare",
  purchase_budget: 0, initial_payment: 0, comfortable_monthly_payment: 0, rent_budget: 0,
  planning_horizon: "3_5_years", car_availability: false,
  transport_preferences: ["public_transport"], preferences,
  price_vs_time: 50, today_vs_future: 50, car_dependency: 50, future_changes: [],
  home_values: [], good_home_text: "", data_processing_consent: false,
  partner: { name: "", work_point: null, transport_preferences: ["public_transport"], preferences: {}, life_goals: [] },
  life_points: [],
};

export const demoDraft: OnboardingDraft = {
  ...initialDraft,
  name: "Максим", household_type: "couple", adults_count: 2, children: [{ age: 7 }],
  housing_goal: "compare", purchase_budget: 12000000, initial_payment: 3000000,
  comfortable_monthly_payment: 75000, rent_budget: 55000, planning_horizon: "3_5_years",
  car_availability: true, transport_preferences: ["car", "public_transport"],
  preferences: { ...preferences, transport_weight: 90, housing_price_weight: 85,
    safety_weight: 85, education_weight: 90, parks_weight: 85, ecology_weight: 85 },
  partner: { name: "Анна", work_point: { latitude: 56.044, longitude: 93.005 },
    transport_preferences: ["public_transport"],
    preferences: { education_weight: 95, parks_weight: 90, ecology_weight: 90 },
    life_goals: ["family_time", "green_environment"] },
  life_points: [
    { localId: "demo-maxim-work", type: "work", name: "Работа Максима — центр", latitude: 56.011, longitude: 92.874, importance: 10, frequency_per_week: 5 },
    { localId: "demo-anna-work", type: "partner_work", name: "Работа Анны", latitude: 56.044, longitude: 93.005, importance: 9, frequency_per_week: 5 },
    { localId: "demo-school", type: "school", name: "Школа ребёнка", latitude: 56.022, longitude: 92.824, importance: 10, frequency_per_week: 5 },
  ],
  home_values: ["family_time", "financial_stability", "green_environment"],
  good_home_text: "Дом, из которого удобно добираться до работы и школы, а рядом есть парк.",
  data_processing_consent: false,
};

type State = {
  step: number;
  draft: OnboardingDraft;
  profileId: string | null;
  setStep: (step: number) => void;
  patch: (patch: Partial<OnboardingDraft>) => void;
  setPreference: (name: PreferenceName, value: number) => void;
  upsertPoint: (point: LifePoint) => void;
  removePoint: (localId: string) => void;
  fillDemo: () => void;
  setProfileId: (id: string) => void;
  reset: () => void;
};

export const useOnboarding = create<State>()(persist((set) => ({
  step: 0, draft: initialDraft, profileId: null,
  setStep: (step) => set({ step: Math.max(0, Math.min(9, step)) }),
  patch: (patch) => set((state) => ({ draft: { ...state.draft, ...patch }, profileId: null })),
  setPreference: (name, value) => set((state) => ({ draft: { ...state.draft,
    preferences: { ...state.draft.preferences, [name]: value } }, profileId: null })),
  upsertPoint: (point) => set((state) => ({ draft: { ...state.draft,
    life_points: [...state.draft.life_points.filter((item) => item.localId !== point.localId), point] }, profileId: null })),
  removePoint: (localId) => set((state) => ({ draft: { ...state.draft,
    life_points: state.draft.life_points.filter((point) => point.localId !== localId) }, profileId: null })),
  fillDemo: () => set({ draft: demoDraft, step: 0, profileId: null }),
  setProfileId: (profileId) => set({ profileId }),
  reset: () => set({ draft: initialDraft, step: 0, profileId: null }),
}), { name: "mesto-onboarding-v1", storage: createJSONStorage(() => localStorage),
  partialize: ({ step, draft, profileId }) => ({ step, draft, profileId }) }));
