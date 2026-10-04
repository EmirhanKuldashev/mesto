import type { MarketAssessment, MarketContext, ObservedAffordability, SampleMetadata } from "@/types/market";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const count = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;
const nullableNumber = (value: unknown) => value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === "string");

function isSample(value: unknown): value is SampleMetadata {
  return record(value) && count(value.observed_count) && count(value.known_price_count) && count(value.unknown_price_count) &&
    value.observed_count === value.known_price_count + value.unknown_price_count && strings(value.source) && strings(value.source_version) &&
    [value.snapshot_date_from, value.snapshot_date_to].every((date) => date === null || (typeof date === "string" && Number.isFinite(Date.parse(date))));
}

function isContext(value: unknown): value is MarketContext {
  return record(value) && count(value.district_id) && value.currency === "RUB" &&
    value.observation_unit === "residential_complex" && value.price_basis === "starting_price" && strings(value.limitations) &&
    [value.min_starting_price, value.median_starting_price, value.max_starting_price].every(nullableNumber) && isSample(value);
}

function isAffordability(value: unknown): value is ObservedAffordability {
  return record(value) && value.methodology_version === "observed-starting-price-v1" && value.ranking_eligible === false &&
    ["purchase", "rent"].includes(String(value.goal)) && ["known_value", "known_zero", "unknown", "not_applicable"].includes(String(value.status)) &&
    ["observed_prices", "no_matches", "budget_missing", "no_observations", "goal_not_selected"].includes(String(value.reason_code)) &&
    value.currency === "RUB" && ["residential_complex", "listing"].includes(String(value.observation_unit)) &&
    ["starting_price", "monthly_rent"].includes(String(value.price_basis)) && nullableNumber(value.budget) &&
    (value.within_budget_count === null || count(value.within_budget_count)) && count(value.known_price_count) &&
    count(value.observed_count) && count(value.unknown_price_count) && nullableNumber(value.budget_to_median_ratio) &&
    nullableNumber(value.within_budget_share) && (value.within_budget_share === null || Number(value.within_budget_share) <= 1) &&
    isSample(value.sample_metadata) && strings(value.limitations);
}

async function read(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(`Данные о жилье недоступны (HTTP ${response.status})`);
  return response.json();
}

export async function getMarketContext(districtId: number, signal: AbortSignal): Promise<MarketContext> {
  const value = await read(await fetch(`${API_URL}/api/market/districts/${districtId}`, { signal, cache: "no-store" }));
  if (!isContext(value) || value.district_id !== districtId) throw new Error("Некорректные данные о стартовых ценах");
  return value;
}

export async function getAffordability(profileId: string, districtId: number, signal: AbortSignal): Promise<MarketAssessment> {
  const value = await read(await fetch(`${API_URL}/api/market/affordability`, {
    method: "POST", headers: { "Content-Type": "application/json" }, signal, cache: "no-store",
    body: JSON.stringify({ profile_id: profileId, district_id: districtId }),
  }));
  if (!record(value) || !isContext(value.market_context) || value.market_context.district_id !== districtId ||
      !record(value.affordability) || !isAffordability(value.affordability.purchase) || !isAffordability(value.affordability.rent) ||
      value.affordability.purchase.goal !== "purchase" || value.affordability.rent.goal !== "rent")
    throw new Error("Некорректные данные сравнения с бюджетом");
  return { market_context: value.market_context, affordability: { purchase: value.affordability.purchase, rent: value.affordability.rent } };
}
