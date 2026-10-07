"use client";

import { useEffect, useMemo, useState } from "react";
import { calculateMobility } from "@/lib/api/mobility";
import type { Coordinate, DestinationKind, MobilityRequest, MobilityResult, PersonalDestination, TravelMode } from "@/types/mobility";

type State = { request: MobilityRequest | null; status: "loading" | "ready" | "error"; result?: MobilityResult; error?: string };
const kinds: Record<DestinationKind, string> = { work: "Работа", university: "Университет", school: "Школа", relatives: "Родственники", other: "Другое" };
const modes: Record<TravelMode, string> = { car: "На машине", public_transport: "Общественный транспорт" };
const inputClass = "mt-1 w-full min-w-0 rounded-lg border border-[#cadbd5] bg-white p-2 text-sm";
function unavailable(reason: string | null) {
  if (reason === "public_transport_source_unavailable") return "Расчёт общественного транспорта пока недоступен: нет подтверждённого источника маршрутов и расписаний.";
  if (reason === "unsupported_geography") return "Одна из точек вне поддерживаемой территории Красноярска и ближайших окрестностей.";
  if (reason === "no_route") return "Дорожный маршрут между этими точками не найден.";
  if (reason === "no_road_segment") return "Не найдена доступная автомобильная дорога в пределах 250 м от одной из точек.";
  if (reason === "provider_rate_limited") return "Сервис маршрутов перегружен. Попробуйте позже.";
  return "Расчёт маршрута временно недоступен. Попробуйте ещё раз.";
}

export function MobilityPanel({ origin }: { origin: Coordinate | null }) {
  const [expanded, setExpanded] = useState(false);
  const [label, setLabel] = useState("Работа");
  const [kind, setKind] = useState<DestinationKind>("work");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [destination, setDestination] = useState<PersonalDestination | null>(null);
  const [mode, setMode] = useState<TravelMode>("car");
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State | null>(null);
  const request = useMemo(() => origin && destination ? { origin, destination, mode } : null, [origin, destination, mode]);
  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    setState({ request, status: "loading" });
    const timer = window.setTimeout(() => {
      controller.abort();
      setState({ request, status: "error", error: "Маршрут не рассчитан вовремя. Повторите запрос." });
    }, 10000);
    void calculateMobility(request, controller.signal).then(result => {
      if (!controller.signal.aborted) setState({ request, status: "ready", result });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({ request, status: "error", error: error instanceof Error ? error.message : "Не удалось рассчитать маршрут" });
    }).finally(() => window.clearTimeout(timer));
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [request, attempt]);
  const current = request ? state?.request === request ? state : { request, status: "loading" } as State : null;
  const result = current?.result;
  return <section aria-labelledby="mobility-heading" style={{ colorScheme: "light" }} className="min-w-0 rounded-[26px] border border-[#c3ded4] bg-white p-5 text-[#14333e] sm:p-6">
    <h2 id="mobility-heading" className="text-xl font-semibold">Важные места</h2>
    <p className="mt-2 text-sm text-[#607f82]">Поездки от выбранного места до работы, учёбы или близких.</p>
    {!expanded && <button type="button" onClick={() => setExpanded(true)} className="mt-4 w-full rounded-xl border border-[#0d766c] px-3 py-3 text-sm font-semibold text-[#0d766c]">Добавить важное место</button>}
    {expanded && <>
      {!origin && <p className="mt-4 text-sm text-[#76562b]">Сначала выберите исходную точку в MESTO Local или на карте.</p>}
      <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); setDestination({ label: label.trim(), kind, latitude: Number(latitude), longitude: Number(longitude) }); }}>
        <label className="block text-xs">Название<input aria-label="Название важного места" required maxLength={80} value={label} onChange={e => { setLabel(e.target.value); setDestination(null); }} className={inputClass} /></label>
        <label className="block text-xs">Тип места<select aria-label="Тип важного места" value={kind} onChange={e => { setKind(e.target.value as DestinationKind); setDestination(null); }} className={inputClass}>{Object.entries(kinds).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
        <div className="grid min-w-0 grid-cols-2 gap-2">
          <label className="min-w-0 text-xs">Широта<input aria-label="Широта важного места" type="number" min="-90" max="90" step="any" required value={latitude} onChange={e => { setLatitude(e.target.value); setDestination(null); }} className={inputClass} /></label>
          <label className="min-w-0 text-xs">Долгота<input aria-label="Долгота важного места" type="number" min="-180" max="180" step="any" required value={longitude} onChange={e => { setLongitude(e.target.value); setDestination(null); }} className={inputClass} /></label>
        </div>
        <div role="group" aria-label="Способ поездки" className="flex flex-col gap-2">{Object.entries(modes).map(([key, title]) => <button key={key} type="button" aria-pressed={mode === key} onClick={() => setMode(key as TravelMode)} className={`w-full rounded-xl border px-3 py-2 text-sm ${mode === key ? "border-[#0d766c] bg-[#e9f8f2] font-semibold" : "border-[#cadbd5]"}`}>{title}</button>)}</div>
        <button type="submit" disabled={!origin} className="w-full rounded-xl bg-[#0d766c] px-3 py-3 text-sm font-semibold text-white disabled:opacity-50">Рассчитать поездку</button>
      </form>
      <div aria-live="polite" aria-atomic="true" className="mt-5">
        {current?.status === "loading" && <p role="status" className="text-sm text-[#607f82]">Рассчитываем маршрут…</p>}
        {current?.status === "error" && <div role="alert" className="text-sm text-[#76562b]"><p>{current.error}</p><button type="button" onClick={() => setAttempt(v => v + 1)} className="mt-2 font-semibold underline">Повторить расчёт поездки</button></div>}
        {result?.availability === "UNAVAILABLE" && <div role="status" className="text-sm text-[#76562b]"><p>{unavailable(result.unavailable_reason)}</p>{mode === "car" && <button type="button" onClick={() => setAttempt(v => v + 1)} className="mt-2 font-semibold underline">Повторить расчёт поездки</button>}</div>}
        {result?.availability === "AVAILABLE" && <>
          <p className="break-words font-semibold">{result.destination.label}</p>
          <p className="mt-1 text-sm text-[#607f82]">{modes[result.mode]}</p>
          <div aria-label="Результат поездки" className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-2xl font-semibold">
            <span>{result.duration_seconds! > 0 && result.duration_seconds! < 60 ? "<1" : Math.ceil(result.duration_seconds! / 60)} мин</span>
            <span>{new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(result.distance_meters! / 1000)} км</span>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-[#607f82]">Расчётное время без учёта текущих пробок. Подход к дороге от исходной точки и до места назначения не включён.</p>
          <p className="mt-2 text-xs text-[#607f82]">Данные дорог: <a className="underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>, ODbL. <a className="underline" href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noreferrer">Исправить карту</a></p>
        </>}
      </div>
    </>}
  </section>;
}
