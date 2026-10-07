"use client";

import { useEffect, useState } from "react";
import { calculateLocal } from "@/lib/api/local";
import { localKeys, type LocalKey, type LocalLocation, type LocalResult } from "@/types/local";

const labels: Record<LocalKey, string> = { stop_availability: "Остановки", school: "Школы",
  kindergarten: "Детские сады", healthcare: "Медицина", parks: "Парки" };
type State = { location: LocalLocation | null; status: "idle" | "loading" | "ready" | "error"; result?: LocalResult; error?: string };

export function LocalPanel({ location, onSelect }: { location: LocalLocation | null; onSelect: (p: LocalLocation) => void }) {
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ location: null, status: "idle" });
  useEffect(() => {
    if (!location) return;
    setLatitude(String(location.latitude)); setLongitude(String(location.longitude));
    const controller = new AbortController();
    setState({ location, status: "loading" });
    const timer = window.setTimeout(() => {
      controller.abort();
      setState({ location, status: "error", error: "Оценка заняла слишком много времени. Повторите запрос." });
    }, 15000);
    void calculateLocal(location, controller.signal).then(result => {
      if (!controller.signal.aborted) setState({ location, status: "ready", result });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({ location, status: "error", error: error instanceof Error ? error.message : "Не удалось оценить место" });
    }).finally(() => window.clearTimeout(timer));
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [location, attempt]);
  const current = state.location === location ? state : { location, status: location ? "loading" : "idle" } as State;
  const result = current.result;
  return <section aria-labelledby="local-heading" style={{ colorScheme: "light" }} className="min-w-0 rounded-[26px] border border-[#c3ded4] bg-white p-5 text-[#14333e] sm:p-6">
    <h2 id="local-heading" className="text-xl font-semibold">MESTO Local</h2>
    {result?.availability === "AVAILABLE" && <p aria-live="polite" aria-label={`MESTO Local: ${Math.round(result.score!)} из 100`} className="mt-3 text-3xl font-semibold">{Math.round(result.score!)} <span className="text-base font-normal text-[#607f82]">/ 100</span></p>}
    <p className="mt-2 text-sm text-[#607f82]">Объективная оценка конкретного места</p>
    <p className="mt-3 text-sm text-[#607f82]">Выберите точку в режиме оценки места на карте или введите координаты.</p>
    <form className="mt-4 space-y-3" onSubmit={event => {
      event.preventDefault(); onSelect({ latitude: Number(latitude), longitude: Number(longitude) });
    }}>
      <div className="grid min-w-0 grid-cols-2 gap-2">
        <label className="min-w-0 text-xs">Широта<input aria-label="Широта места" type="number" min="-90" max="90" step="any" required value={latitude} onChange={event => setLatitude(event.target.value)} className="mt-1 w-full min-w-0 rounded-lg border border-[#cadbd5] p-2 text-sm" /></label>
        <label className="min-w-0 text-xs">Долгота<input aria-label="Долгота места" type="number" min="-180" max="180" step="any" required value={longitude} onChange={event => setLongitude(event.target.value)} className="mt-1 w-full min-w-0 rounded-lg border border-[#cadbd5] p-2 text-sm" /></label>
      </div>
      <button type="submit" className="w-full rounded-xl bg-[#0d766c] px-3 py-3 text-sm font-semibold text-white">Оценить место</button>
    </form>
    <div aria-live="polite" aria-atomic="true" className="mt-5">
      {current.status === "loading" && <p role="status" className="text-sm text-[#607f82]">Оцениваем выбранное место…</p>}
      {current.status === "error" && <div role="alert" className="text-sm text-[#76562b]"><p>{current.error}</p><button type="button" onClick={() => setAttempt(v => v + 1)} className="mt-2 font-semibold underline">Повторить оценку места</button></div>}
      {result?.availability === "UNAVAILABLE" && <p role="status" className="text-sm text-[#76562b]">{result.unavailable_reason === "unsupported_geography" ? "Точка вне поддерживаемой территории Красноярска." : "Оценка места недоступна: недостаточно подтверждённых данных."}</p>}
      {result?.availability === "AVAILABLE" && <>
        <dl className="mt-4 space-y-3">{localKeys.map(key => {
          const c = result.components[key];
          return <div key={key} className="border-t border-[#e1ebe7] pt-3">
            <div className="flex items-center justify-between gap-2"><dt className="text-sm">{labels[key]}</dt><dd className="font-semibold">{Math.round(c.score!)}</dd></div>
            <p className="mt-1 break-words text-xs text-[#607f82]">~{Math.round(c.distance_m!)} м · {c.nearest?.name ?? "Объект без названия"}</p>
            {key === "healthcare" && <p className="mt-1 text-xs text-[#607f82]">{c.nearest?.category === "hospital" ? "Больница" : "Клиника"}</p>}
            {key === "parks" && c.inside_geometry && <p className="mt-1 text-xs text-[#0d766c]">Выбранная точка находится внутри парка или на его границе.</p>}
          </div>;
        })}</dl>
        <p className="mt-4 text-xs leading-relaxed text-[#607f82]">Сравнение с распределением по Красноярску. Расстояния по прямой; качество услуг и пешие маршруты не оцениваются.</p>
      </>}
    </div>
  </section>;
}
