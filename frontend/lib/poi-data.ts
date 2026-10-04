import type { GeoPoint, Poi } from "./complex-scoring";

export function isPoint(value: unknown): value is GeoPoint {
  if (!value || typeof value !== "object") return false;
  const point = value as Record<string, unknown>;
  return point.type === "Point" && Array.isArray(point.coordinates) && point.coordinates.length === 2 &&
    point.coordinates.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate));
}

export function isPoi(value: unknown): value is Poi {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.source_id === "osm" && item.is_synthetic === false && typeof item.id === "number" &&
    (item.name === null || typeof item.name === "string") && typeof item.category === "string" &&
    (item.district_id === null || typeof item.district_id === "number") && isPoint(item.location);
}
