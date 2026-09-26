import type { DistrictScoreResponse } from "@/types/analytics";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class AnalyticsApiError extends Error {
  constructor(message: string) { super(message); this.name = "AnalyticsApiError"; }
}

async function readResponse(response: Response): Promise<unknown> {
  if (!response.ok) throw new AnalyticsApiError(`API вернул HTTP ${response.status}`);
  try { return await response.json(); }
  catch { throw new AnalyticsApiError("API вернул некорректный JSON"); }
}

function isScore(value: unknown): value is DistrictScoreResponse {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  const district = item.district as Record<string, unknown> | null;
  const categories = item.categories as Record<string, unknown> | null;
  return typeof item.id === "number" && typeof district?.id === "number" &&
    typeof district.name === "string" && typeof categories === "object" && categories !== null &&
    ["lifestyle", "infrastructure", "transport", "future_growth", "market"].every(
      (key) => categories[key] === null || typeof categories[key] === "number") &&
    ["score", "current_score", "future_score", "future_growth_score"].every(
      (key) => item[key] === null || typeof item[key] === "number") &&
    typeof item.confidence === "number" && Array.isArray(item.reasons) &&
    Array.isArray(item.warnings) && Array.isArray(item.future_factors);
}

export async function getDistrictIds(onStage?: (stage: "districts") => void): Promise<number[]> {
  onStage?.("districts");
  const payload = await readResponse(await fetch(`${API_URL}/api/districts`, { cache: "no-store" }));
  if (!Array.isArray(payload)) throw new AnalyticsApiError("API районов вернул некорректные данные");
  return [...new Set(payload.map((row) => row && typeof row === "object" ? (row as { id?: unknown }).id : null)
    .filter((id): id is number => typeof id === "number" && Number.isInteger(id) && id > 0))];
}

export async function calculateScore(profileId: string, districtIds: number[],
                                     onStage?: (stage: "scoring") => void): Promise<DistrictScoreResponse[]> {
  if (!profileId || districtIds.length === 0) return [];
  onStage?.("scoring");
  const results: DistrictScoreResponse[] = [];
  for (let index = 0; index < districtIds.length; index += 50) {
    const response = await fetch(`${API_URL}/api/analytics/score`, {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      body: JSON.stringify({ profile_id: profileId, district_ids: districtIds.slice(index, index + 50) }),
    });
    const payload = await readResponse(response);
    if (!Array.isArray(payload) || !payload.every(isScore))
      throw new AnalyticsApiError("API аналитики вернул некорректные данные");
    results.push(...payload);
  }
  return results;
}
