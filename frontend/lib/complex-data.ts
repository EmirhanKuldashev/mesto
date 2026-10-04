"use client";

import { useEffect, useState } from "react";
import type { Complex, District, FutureObject, GeoPoint, Poi } from "@/lib/complex-scoring";

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

export function isPoi(value: unknown): value is Poi {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.source_id === "osm" && item.is_synthetic === false && typeof item.id === "number" &&
    (item.name === null || typeof item.name === "string") && typeof item.category === "string" &&
    (item.district_id === null || typeof item.district_id === "number") && isPoint(item.location);
}

function isFutureObject(value: unknown): value is FutureObject {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === "number" && typeof item.name === "string" && typeof item.category === "string" &&
    (item.district_id === null || typeof item.district_id === "number") &&
    (item.location === null || isPoint(item.location)) && typeof item.status === "string" &&
    (item.planned_year === null || typeof item.planned_year === "number") &&
    typeof item.is_synthetic === "boolean" && typeof item.source_id === "string";
}

export function useComplexData() {
  const [complexes, setComplexes] = useState<Complex[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [pois, setPois] = useState<Poi[]>([]);
  const [futureObjects, setFutureObjects] = useState<FutureObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const paths = ["/api/residential-complexes?source_id=cian", "/api/poi?source_id=osm",
      "/api/districts?source_id=osm", "/api/future-objects?source_id=osm"];
    Promise.all(paths.map(async (path) => {
      const response = await fetch(`${base}${path}`, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error(`Геоданные недоступны (HTTP ${response.status})`);
      const payload: unknown = await response.json();
      if (!Array.isArray(payload)) throw new Error("Некорректный ответ API геоданных");
      return payload;
    })).then(([complexPayload, poiPayload, districtPayload, futurePayload]) => {
      if (!controller.signal.aborted) {
        setComplexes(complexPayload.filter(isComplex)); setPois(poiPayload.filter(isPoi));
        setDistricts(districtPayload.filter(isDistrict)); setFutureObjects(futurePayload.filter(isFutureObject));
        setError(null);
      }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить карту");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  return { complexes, pois, districts, futureObjects, loading, error };
}
