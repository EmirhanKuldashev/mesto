import type { DistrictScoreResponse } from "@/types/analytics";

// Explicit sample data, shown only with a Demo mode label.
export const demoScores: DistrictScoreResponse[] = [{
  id: 0, district: { id: 0, name: "Пример района", slug: null },
  score: 86, current_score: 82, future_score: 86, future_growth_score: 27,
  categories: { lifestyle: 85, infrastructure: 80, transport: 78, future_growth: 27, market: 72 },
  future_factors: [{ object_id: 0, name: "Новая школа (пример)", type: "school", year: 2028,
    status: "planned", impact: { education: 8, family: 5, infrastructure: 5 },
    reason: "Новый объект образования", distance_km: 1, confidence: .7, is_synthetic: true }],
  future_impacts: { education: 8, family: 5, infrastructure: 5 }, external_signal_impacts: [], confidence: .5,
  reasons: ["Пример: рядом находятся образовательные объекты"],
  warnings: ["Демонстрационные значения не относятся к реальному району"],
  is_synthetic: true, calculation_version: "demo", created_at: new Date(0).toISOString(),
}];
