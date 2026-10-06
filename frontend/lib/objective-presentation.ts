import type { DistrictScoreResponse } from "@/types/analytics";

export const objectiveComponents = [
  { key: "stop_availability", label: "Остановки", description: "Близость к наблюдаемым остановкам общественного транспорта" },
  { key: "school", label: "Школы", description: "Близость к наблюдаемым школам" },
  { key: "kindergarten", label: "Детские сады", description: "Близость к наблюдаемым детским садам" },
  { key: "healthcare", label: "Медицина", description: "Близость к наблюдаемым клиникам и больницам" },
  { key: "parks", label: "Парки", description: "Близость к наблюдаемой геометрии парков" },
] as const;

export function isDisplayScore(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
}

// Read the canonical result; never recalculate it or substitute a legacy score.
export function objectiveValue(score?: DistrictScoreResponse): number | null {
  const objective = score?.objective;
  if (objective?.calculation_version !== "objective-mesto-v2" ||
      objective.availability !== "AVAILABLE" || !isDisplayScore(objective.score)) return null;
  return objective.score;
}

export function displayScore(value: number | null): string {
  return value === null ? "—" : String(Math.round(value));
}

// Backend diagnostics can contain paths and arbitrary exception text. Do not echo them.
export function unavailableExplanation(reason?: string | null): string {
  if (reason === "dataset_unavailable") return "Подтверждённые данные территории пока недоступны.";
  return "Для оценки нужны подтверждённые данные всех пяти компонентов. Попробуйте позже.";
}
