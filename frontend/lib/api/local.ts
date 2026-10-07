import { localKeys, type LocalLocation, type LocalResult } from "@/types/local";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const score = (v: unknown) => finite(v) && v >= 0 && v <= 100;

export function isLocalResult(value: unknown): value is LocalResult {
  if (!record(value) || value.version !== "local-objective-v1" || !record(value.location) ||
      !finite(value.location.latitude) || Math.abs(value.location.latitude) > 90 ||
      !finite(value.location.longitude) || Math.abs(value.location.longitude) > 180 ||
      !record(value.components) || Object.keys(value.components).length !== 5 || !record(value.weights) ||
      !Array.isArray(value.limitations) || !value.limitations.every(v => typeof v === "string") || !record(value.provenance)) return false;
  const components = value.components;
  const weights = value.weights;
  if (!localKeys.every(key => {
    const c = components[key];
    if (!record(c) || c.key !== key || weights[key] !== .2 || typeof c.available !== "boolean" ||
        !["normalization_version", "evidence_version", "eligibility_version", "reference_id", "reference_checksum", "distance_method"].every(k => typeof c[k] === "string") ||
        !Array.isArray(c.limitations) || !record(c.provenance) ||
        (key === "parks" ? typeof c.inside_geometry !== "boolean" && c.inside_geometry !== null : c.inside_geometry !== null)) return false;
    if (!c.available) return c.score === null && c.nearest === null && typeof c.unavailable_reason === "string" && !!c.unavailable_reason;
    const nearest = c.nearest;
    return score(c.score) && finite(c.distance_m) && c.distance_m >= 0 && c.unavailable_reason === null &&
      record(nearest) && nearest.source_id === "osm" && ["node", "way", "relation"].includes(String(nearest.osm_type)) &&
      finite(nearest.osm_id) && Number.isInteger(nearest.osm_id) && nearest.osm_id > 0 &&
      (nearest.name === null || typeof nearest.name === "string") && nearest.distance_m === c.distance_m &&
      (key === "healthcare" ? ["clinic", "hospital"].includes(String(nearest.category)) :
        nearest.category === (key === "stop_availability" ? "bus_stop" : key === "parks" ? "park" : key));
  })) return false;
  const ready = localKeys.every(key => (components[key] as Record<string, unknown>).available === true);
  return value.availability === "AVAILABLE" ? ready && score(value.score) && value.unavailable_reason === null :
    value.availability === "UNAVAILABLE" && !ready && value.score === null && typeof value.unavailable_reason === "string" && !!value.unavailable_reason;
}

export async function calculateLocal(location: LocalLocation, signal: AbortSignal): Promise<LocalResult> {
  const response = await fetch(`${API_URL}/api/analytics/local`, { method: "POST", cache: "no-store", signal,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(location) });
  if (!response.ok) throw new Error(`Не удалось оценить место (HTTP ${response.status})`);
  const payload: unknown = await response.json();
  if (!isLocalResult(payload) || payload.location.latitude !== location.latitude || payload.location.longitude !== location.longitude)
    throw new Error("Получен некорректный результат оценки места");
  return payload;
}
