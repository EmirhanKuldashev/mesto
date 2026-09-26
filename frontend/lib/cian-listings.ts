"use client";

import { useEffect, useState } from "react";

export type CianListing = {
  id: number;
  district_id: number | null;
  external_id: string;
  source_id: "cian";
  title: string | null;
  url: string;
  price: number;
  area_sqm: number;
  rooms: number | null;
  floor: number | null;
  address: string | null;
  city: string | null;
  fetched_at: string;
};

function isCianListing(value: unknown): value is CianListing {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return item.source_id === "cian" && item.is_synthetic === false &&
    typeof item.id === "number" && (item.district_id === null || typeof item.district_id === "number") &&
    typeof item.external_id === "string" &&
    typeof item.url === "string" && /^https:\/\/([a-z0-9-]+\.)?cian\.ru\/sale\/flat\/\d+\/?$/.test(item.url) &&
    typeof item.price === "number" && Number.isFinite(item.price) &&
    typeof item.area_sqm === "number" && item.area_sqm > 0 &&
    typeof item.fetched_at === "string";
}

export function useCianListings() {
  const [listings, setListings] = useState<CianListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${apiUrl}/api/properties?source_id=cian`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`API вернул HTTP ${response.status}`);
        const payload: unknown = await response.json();
        if (!Array.isArray(payload)) throw new Error("Некорректный ответ API");
        return payload.filter(isCianListing);
      })
      .then((items) => { setListings(items); setError(null); })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить объявления");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  return { listings, loading, error };
}

export const formatPrice = (price: number) => `${new Intl.NumberFormat("ru-RU").format(price)} ₽`;
export const formatArea = (area: number) => `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(area)} м²`;
