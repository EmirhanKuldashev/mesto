import type { OnboardingDraft } from "@/lib/onboarding-store";

export type GeoPoint = { type: "Point"; coordinates: [number, number] };
export type Complex = {
  id: number;
  name: string;
  url: string | null;
  price_from: number | null;
  district_id: number | null;
  location: GeoPoint | null;
  source_id: string;
  is_synthetic: boolean;
};
export type Poi = { id: number; category: string; location: GeoPoint; source_id: string; is_synthetic: boolean };
export type Score = { value: number | null; coverage: number; reasons: string[] };
export type ScoredComplex = Complex & { score: Score };
export type District = { id: number; name: string; geometry: { type: "MultiPolygon"; coordinates: number[][][][] }; centroid: GeoPoint | null; source_id: string; is_synthetic: boolean };
export type ScoredDistrict = District & { value: number | null; coverage: number; complexes: ScoredComplex[] };

const EARTH_METERS_PER_DEGREE = 111_320;
const clamp = (value: number) => Math.max(0, Math.min(1, value));

function distanceMeters(a: [number, number], b: [number, number]) {
  const latitude = (a[1] + b[1]) / 2 * Math.PI / 180;
  const x = (a[0] - b[0]) * Math.cos(latitude) * EARTH_METERS_PER_DEGREE;
  const y = (a[1] - b[1]) * EARTH_METERS_PER_DEGREE;
  return Math.hypot(x, y);
}

function nearestScore(point: [number, number], pois: Poi[], categories: string[], radius: number) {
  let nearest = Infinity;
  for (const poi of pois) {
    if (!categories.includes(poi.category) || poi.source_id !== "osm" || poi.is_synthetic) continue;
    nearest = Math.min(nearest, distanceMeters(point, poi.location.coordinates));
  }
  return Number.isFinite(nearest) ? clamp(1 - nearest / radius) : null;
}

export function scoreComplex(complex: Complex, pois: Poi[], draft: OnboardingDraft): Score {
  if (!complex.location || complex.source_id !== "cian" || complex.is_synthetic) {
    return { value: null, coverage: 0, reasons: ["Нет подтверждённых координат ЖК"] };
  }
  const point = complex.location.coordinates;
  let requested = 0;
  let measured = 0;
  let weighted = 0;
  const reasons: string[] = [];
  const add = (label: string, weight: number, value: number | null) => {
    if (weight <= 0) return;
    requested += weight;
    if (value === null) { reasons.push(`${label}: данных нет`); return; }
    measured += weight;
    weighted += weight * value;
    reasons.push(`${label}: ${Math.round(value * 100)}%`);
  };
  const preferenceWeight = (name: keyof OnboardingDraft["preferences"]) => {
    const answers = [draft.preferences[name], draft.partner.preferences[name]].filter(
      (answer) => answer?.is_answered && answer.value !== null && answer.confidence > 0,
    );
    return answers.length ? answers.reduce((sum, answer) => sum + answer!.value! / 100 * answer!.confidence, 0) / answers.length : 0;
  };
  if (draft.housing_goal !== "rent" && draft.purchase_budget > 0) {
    add("Бюджет", 1 + preferenceWeight("housing_price_weight"),
      complex.price_from && complex.price_from > 0 ? clamp(draft.purchase_budget / complex.price_from) : null);
  }
  const hasChildren = draft.children.length > 0;
  const needsKindergarten = draft.children.some((child) => child.age < 7) || draft.future_changes.includes("child");
  add("Школа", (hasChildren ? 1 : 0) + preferenceWeight("education_weight"), nearestScore(point, pois, ["school"], 3000));
  add("Детский сад", (needsKindergarten ? 1 : 0) + preferenceWeight("kindergarten_weight"), nearestScore(point, pois, ["kindergarten"], 2500));
  add("Парк", preferenceWeight("parks_weight") + preferenceWeight("ecology_weight"), nearestScore(point, pois, ["park"], 3000));
  add("Медицина", preferenceWeight("healthcare_weight"), nearestScore(point, pois, ["hospital", "clinic"], 4000));
  add("Остановка", preferenceWeight("transport_weight"), nearestScore(point, pois, ["bus_stop"], 1800));
  for (const lifePoint of draft.life_points) {
    const weight = lifePoint.importance / 10 * lifePoint.frequency_per_week / 7;
    if (weight > 0) add(`Точка: ${lifePoint.name}`, weight,
      clamp(1 - distanceMeters(point, [lifePoint.longitude, lifePoint.latitude]) / 15_000));
  }
  return { value: measured ? clamp(weighted / measured) : null,
    coverage: requested ? clamp(measured / requested) : 0, reasons };
}

export function scoreDistricts(districts: District[], complexes: ScoredComplex[]): ScoredDistrict[] {
  return districts.map((district) => {
    const members = complexes.filter((complex) => complex.district_id === district.id);
    const measured = members.filter((complex) => complex.score.value !== null);
    return { ...district, complexes: members,
      value: measured.length ? measured.reduce((total, complex) => total + complex.score.value!, 0) / measured.length : null,
      coverage: measured.length ? measured.reduce((total, complex) => total + complex.score.coverage, 0) / measured.length : 0,
    };
  });
}

export function scoreColor(value: number | null) {
  if (value === null) return "#94a3b8";
  if (value < .4) return "#ef6b63";
  if (value < .7) return "#f4bd4c";
  return "#42bc91";
}
