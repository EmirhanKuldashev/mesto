"use client";

import Link from "next/link";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import type { DistrictRecommendation } from "@/types/recommendations";

export function RecommendationPanel({ items, error, selectedId, onSelect, onRetry }: {
  items: DistrictRecommendation[];
  error: string | null;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onRetry: () => void;
}) {
  return <section className="rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
    <div className="flex flex-wrap items-center justify-between gap-4"><div>
      <p className="text-xs font-bold uppercase tracking-[.15em] text-[#168e79]">Персональный подбор</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-[-.04em]">Ваши лучшие места</h2>
    </div><Sparkles size={24} className="text-[#168e79]" /></div>
    <p className="mt-3 max-w-2xl text-sm text-[#647f80]">Match Score показывает персональное соответствие. MESTO Score — базовый индекс текущей инфраструктуры и доступности остановок.</p>
    {error && <div role="alert" className="mt-5 text-sm text-[#a15c49]">Не удалось получить рекомендации: {error}. <button type="button" onClick={onRetry} className="font-semibold underline">Повторить</button></div>}
    {!error && items.length === 0 && <p className="mt-5 text-sm text-[#647f80]">Пока нет районов с достаточными данными для персонального подбора.</p>}
    {items.length > 0 && <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map((item) =>
      <article key={item.district_id} className={`rounded-[22px] border p-5 ${selectedId === item.district_id ? "border-[#25ad8d] bg-[#eaf8f2]" : "border-[#e1ebe7] bg-[#f7faf8]"}`}>
        <button type="button" onClick={() => onSelect(item.district_id)} aria-pressed={selectedId === item.district_id} className="w-full text-left">
          <p className="text-xs font-bold uppercase tracking-[.14em] text-[#168e79]">{item.rank} место</p>
          <div className="mt-2 flex items-start justify-between gap-3"><h3 className="text-xl font-semibold">{item.district_name}</h3><span className="shrink-0 text-2xl font-bold text-[#168e79]">{Math.round(item.match_score)}%</span></div>
          <p className="mt-2 text-xs text-[#547477]">Match Score · MESTO Score {item.district_score === null ? "—" : `${Math.round(item.district_score)}/100`}</p>
        </button>
        <h4 className="mt-4 text-sm font-semibold">Почему подходит</h4>
        {item.reasons.length ? <ul className="mt-2 space-y-2">{item.reasons.slice(0, 3).map((reason, index) => <li key={index} className="flex gap-2 text-sm leading-relaxed text-[#547477]"><Check size={16} className="mt-0.5 shrink-0 text-[#168e79]" />{reason}</li>)}</ul>
          : <p className="mt-2 text-sm text-[#647f80]">Подробных причин пока нет.</p>}
        <Link href={`/district?districtId=${item.district_id}`} className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0d766c]">Район на карте <ArrowRight size={15} /></Link>
      </article>)}</div>}
  </section>;
}
