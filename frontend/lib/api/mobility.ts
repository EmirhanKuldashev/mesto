import type { Coordinate, MobilityRequest, MobilityResult } from "@/types/mobility";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const metric = (v: unknown): v is number => finite(v) && v >= 0;
const coordinate = (v: unknown): v is Coordinate => record(v) && finite(v.latitude) && Math.abs(v.latitude) <= 90 && finite(v.longitude) && Math.abs(v.longitude) <= 180;
const same = (v: Coordinate, p: Coordinate) => v.latitude === p.latitude && v.longitude === p.longitude;
const nullableString = (v: unknown) => v === null || typeof v === "string";

export function isMobilityResult(v: unknown, request: MobilityRequest): v is MobilityResult {
  if (!record(v) || v.version !== "mobility-v1" || v.mode !== request.mode || v.departure_time !== null ||
      v.traffic !== (request.mode === "car" ? "not_included" : "not_available") ||
      !record(v.destination) || v.destination.label !== request.destination.label || v.destination.kind !== request.destination.kind ||
      !coordinate(v.origin) || !same(v.origin, request.origin) || !coordinate(v.destination) || !same(v.destination, request.destination) ||
      !Array.isArray(v.limitations) || !v.limitations.every(s => typeof s === "string") ||
      ![v.provider, v.provider_version, v.data_timestamp, v.dataset_id, v.dataset_sha256].every(nullableString)) return false;
  if (v.availability === "UNAVAILABLE") return typeof v.unavailable_reason === "string" && !!v.unavailable_reason &&
    [v.duration_seconds, v.distance_meters, v.geometry, v.origin_snap, v.destination_snap].every(x => x === null);
  if (v.availability !== "AVAILABLE" || !metric(v.duration_seconds) || !metric(v.distance_meters) || v.unavailable_reason !== null ||
      typeof v.provider !== "string" || !v.provider || typeof v.provider_version !== "string" || !v.provider_version) return false;
  const snap = (s: unknown) => record(s) && coordinate(s.location) && metric(s.distance_meters) && s.distance_meters <= 250;
  return (v.origin_snap === null || snap(v.origin_snap)) && (v.destination_snap === null || snap(v.destination_snap)) &&
    (v.geometry === null || (record(v.geometry) && v.geometry.type === "LineString" &&
      Array.isArray(v.geometry.coordinates) && v.geometry.coordinates.length >= 2 && v.geometry.coordinates.length <= 20000 &&
      v.geometry.coordinates.every(p => Array.isArray(p) && p.length === 2 && finite(p[0]) && Math.abs(p[0]) <= 180 && finite(p[1]) && Math.abs(p[1]) <= 90)));
}

export async function calculateMobility(request: MobilityRequest, signal: AbortSignal): Promise<MobilityResult> {
  const response = await fetch(`${API_URL}/api/analytics/mobility`, { method: "POST", cache: "no-store", signal,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
  if (!response.ok) throw new Error(`Не удалось рассчитать маршрут (HTTP ${response.status})`);
  const payload: unknown = await response.json();
  if (!isMobilityResult(payload, request)) throw new Error("Получен некорректный результат маршрута");
  return payload;
}
