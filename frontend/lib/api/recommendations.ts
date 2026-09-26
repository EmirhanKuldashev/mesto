import type { RecommendationResponse } from "@/types/recommendations";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getRecommendations(profileId: string): Promise<RecommendationResponse> {
  const response = await fetch(`${API_URL}/api/recommendations`, {
    method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!response.ok) throw new Error(`Не удалось получить рекомендации (HTTP ${response.status})`);
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" ||
      !Array.isArray((payload as RecommendationResponse).recommendations) ||
      !(payload as RecommendationResponse).recommendations.every((item) =>
        item && typeof item.district_id === "number" && typeof item.district_name === "string" &&
        typeof item.match_score === "number" && typeof item.rank === "number" &&
        Array.isArray(item.reasons) && Array.isArray(item.warnings))) {
    throw new Error("API рекомендаций вернул некорректные данные");
  }
  return payload as RecommendationResponse;
}
