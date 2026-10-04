"use client";

import { useEffect, useState } from "react";
import { getAffordability, getMarketContext } from "@/lib/api/market";
import type { MarketAssessment, MarketContext } from "@/types/market";

type Result = { key: string; context?: MarketContext; assessment?: MarketAssessment; error?: string; comparisonError?: string };
const money = (value: number) => `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value)} ₽`;
const date = (value: string | null) => value ? new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)) : "неизвестна";

export function DistrictMarket({ districtId, profileId }: { districtId: number; profileId: string | null }) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const key = `${districtId}:${profileId}:${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => controller.abort(), 15000);
    const message = (error: unknown) => controller.signal.aborted ? "Запрос занял слишком много времени. Повторите загрузку." :
      error instanceof Error ? error.message : "Не удалось получить данные о жилье.";
    void Promise.allSettled([
      getMarketContext(districtId, controller.signal),
      profileId ? getAffordability(profileId, districtId, controller.signal) : Promise.resolve(null),
    ]).then(([context, assessment]) => {
      if (!active) return;
      setResult({ key,
        context: context.status === "fulfilled" ? context.value : undefined,
        error: context.status === "rejected" ? message(context.reason) : undefined,
        assessment: assessment.status === "fulfilled" ? assessment.value ?? undefined : undefined,
        comparisonError: assessment.status === "rejected" ? message(assessment.reason) : undefined,
      });
    }).finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [districtId, profileId, key]);
  const current = result?.key === key ? result : null;
  const context = current?.context ?? current?.assessment?.market_context;
  const purchase = current?.assessment?.affordability.purchase;
  const rent = current?.assessment?.affordability.rent;
  const limitations = [...new Set([...(context?.limitations ?? []), ...(purchase?.limitations ?? [])])];
  return <section aria-label="Стартовые цены ЖК" className="mt-8 rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
    <h2 className="text-2xl font-semibold">Стартовые цены ЖК</h2>
    {!current && <p role="status" className="mt-4 text-sm text-[#607f82]">Загружаем наблюдаемые стартовые цены…</p>}
    {current?.error && !context && <p role="alert" className="mt-4 text-sm text-[#76562b]">{current.error}</p>}
    {context && <>
      {context.known_price_count > 0 ? <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        {[['От', context.min_starting_price], ['Медиана', context.median_starting_price], ['До', context.max_starting_price]].map(([label, value]) =>
          <div key={String(label)}><dt className="text-sm text-[#607f82]">{label}</dt><dd className="mt-1 text-xl font-semibold">{value === null ? "Неизвестно" : money(value as number)}</dd></div>)}
      </dl> : <p className="mt-4 text-sm">{context.observed_count ? "У учтённых ЖК стартовые цены неизвестны." : "В текущем снимке нет наблюдаемых ЖК по району."}</p>}
      <p className="mt-4 text-sm">{context.known_price_count} из {context.observed_count} ЖК имеют известную стартовую цену.</p>
      <p className="mt-2 text-sm text-[#607f82]">У {context.unknown_price_count} ЖК стартовая цена неизвестна.</p>
      <div className="mt-5 rounded-xl bg-[#f1f8f5] p-4 text-sm" aria-label="Сравнение стартовых цен с бюджетом">
        {purchase?.status === "known_value" && <p>В {purchase.within_budget_count} из {purchase.known_price_count} ЖК с известной стартовой ценой стартовая цена не превышает ваш бюджет{purchase.budget !== null ? ` ${money(purchase.budget)}` : ""}.</p>}
        {purchase?.status === "known_zero" && <p>Среди {purchase.known_price_count} учтённых ЖК с известной стартовой ценой нет совпадений в пределах вашего бюджета. Это не означает отсутствие подходящего жилья в районе.</p>}
        {purchase?.status === "unknown" && <p>{purchase.reason_code === "budget_missing" ? "Укажите бюджет покупки, чтобы сравнить его со стартовыми ценами." : "Недостаточно наблюдаемых стартовых цен для сравнения с бюджетом покупки."}</p>}
        {!profileId && <p>Заполните анкету и укажите бюджет покупки для сравнения со стартовыми ценами.</p>}
        {current?.comparisonError && <p role="alert">Сравнение с бюджетом недоступно: {current.comparisonError}</p>}
        {rent?.status === "unknown" && <p className={purchase?.status !== "not_applicable" ? "mt-2" : ""}>В текущем снимке нет данных аренды по району. Сравнение с бюджетом аренды недоступно.</p>}
      </div>
      <ul className="mt-5 space-y-2 text-xs leading-relaxed text-[#607f82]">{limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
      <p className="mt-4 text-xs text-[#607f82]">Источник: {context.source.join(", ") || "нет наблюдений"}. Версии: {context.source_version.join(", ") || "неизвестны"}.</p>
      <p className="mt-1 text-xs text-[#607f82]">Даты записей источника (UTC): {date(context.snapshot_date_from)} — {date(context.snapshot_date_to)}.</p>
    </>}
    {(current?.error || current?.comparisonError) && <button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-3 text-sm font-semibold text-[#138d7b] underline">Повторить загрузку</button>}
  </section>;
}
