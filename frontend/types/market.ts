export type SampleMetadata = {
  observed_count: number;
  known_price_count: number;
  unknown_price_count: number;
  source: string[];
  source_version: string[];
  snapshot_date_from: string | null;
  snapshot_date_to: string | null;
};

export type MarketContext = SampleMetadata & {
  district_id: number;
  min_starting_price: number | null;
  median_starting_price: number | null;
  max_starting_price: number | null;
  currency: "RUB";
  observation_unit: "residential_complex";
  price_basis: "starting_price";
  limitations: string[];
};

export type ObservedAffordability = {
  methodology_version: "observed-starting-price-v1";
  goal: "purchase" | "rent";
  status: "known_value" | "known_zero" | "unknown" | "not_applicable";
  reason_code: "observed_prices" | "no_matches" | "budget_missing" | "no_observations" | "goal_not_selected";
  budget: number | null;
  currency: "RUB";
  observation_unit: "residential_complex" | "listing";
  price_basis: "starting_price" | "monthly_rent";
  within_budget_count: number | null;
  known_price_count: number;
  observed_count: number;
  unknown_price_count: number;
  within_budget_share: number | null;
  budget_to_median_ratio: number | null;
  sample_metadata: SampleMetadata;
  limitations: string[];
  ranking_eligible: false;
};

export type MarketAssessment = {
  market_context: MarketContext;
  affordability: { purchase: ObservedAffordability; rent: ObservedAffordability };
};
