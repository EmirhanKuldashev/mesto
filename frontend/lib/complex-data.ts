"use client";

import { useEffect, useState } from "react";
import type { Complex, District, GeoPoint, Poi } from "@/lib/complex-scoring";

function isPoint(value: unknown): value is GeoPoint {
  if (!value || typeof value !== "object") return false;
  const point = value as Record<string, unknown>;
  return point.type === "Point" && Array.isArray(point.coordinates) && point.coordinates.length === 2 &&
    point.coordinates.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate));
}

function isComplex(value: unknown): value is Complex {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.source_id === "cian" && item.is_synthetic === false && typeof item.id === "number" &&
    typeof item.name === "string" && (item.location === null || isPoint(item.location)) &&
    (item.district_id === null || typeof item.district_id === "number") &&
    (item.price_from === null || typeof item.price_from === "number");
}

function isDistrict(value: unknown): value is District {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  const geometry = item.geometry as Record<string, unknown> | null;
  return item.source_id === "osm" && item.is_synthetic === false && typeof item.id === "number" &&
    typeof item.name === "string" && geometry?.type === "MultiPolygon" && Array.isArray(geometry.coordinates) &&
    (item.centroid === null || isPoint(item.centroid));
}

function isPoi(value: unknown): value is Poi {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.source_id === "osm" && item.is_synthetic === false && typeof item.id === "number" &&
    typeof item.category === "string" && isPoint(item.location);
}

export function useComplexData() {
  const [complexes, setComplexes] = useState<Complex[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [pois, setPois] = useState<Poi[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    Promise.all([
      fetch(`${base}/api/residential-complexes?source_id=cian`, { signal: controller.signal, cache: "no-store" }),
      fetch(`${base}/api/poi?source_id=osm`, { signal: controller.signal, cache: "no-store" }),
      fetch(`${base}/api/districts?source_id=osm`, { signal: controller.signal, cache: "no-store" }),
    ]).then(async ([complexResponse, poiResponse, districtResponse]) => {
      if (!complexResponse.ok || !poiResponse.ok || !districtResponse.ok) throw new Error("Не удалось получить ЖК, районы или инфраструктуру из API");
      const [complexPayload, poiPayload, districtPayload]: unknown[] = await Promise.all([complexResponse.json(), poiResponse.json(), districtResponse.json()]);
      if (!Array.isArray(complexPayload) || !Array.isArray(poiPayload) || !Array.isArray(districtPayload)) throw new Error("Некорректный ответ API");
      return { complexes: complexPayload.filter(isComplex), pois: poiPayload.filter(isPoi), districts: districtPayload.filter(isDistrict) };
    }).then((data) => {
      if (!controller.signal.aborted) { setComplexes(data.complexes); setPois(data.pois); setDistricts(data.districts); setError(null); }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить данные");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  return { complexes, pois, districts, loading, error };
}
