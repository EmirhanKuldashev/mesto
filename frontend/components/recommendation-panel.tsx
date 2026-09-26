"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { getRecommendations } from "@/lib/api/recommendations";
import type { DistrictRecommendation } from "@/types/recommendations";

export function RecommendationPanel({ profileId }: { profileId: string }) {
  const [items, setItems] = useState<DistrictRecommendation[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try { setItems((await getRecommendations(profileId)).recommendations); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось получить рекомендации"); }
    finally { setLoading(false); }
  }

  return <section className="mt-8 rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
    <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[.15em] text-[#168e79]">Персональный подбор</p><h2 className="mt-2 text-2xl font-semibold tracking-[-.04em]">Районы для вас</h2></div>
      <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-full bg-[#0d766c] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"><Sparkles size={16} />{loading ? "Подбираем…" : items ? "Обновить подбор" : "Подобрать районы"}</button></div>
    <p className="mt-3 max-w-2xl text-sm text-[#647f80]">Подбор учитывает ваши приоритеты отдельно от общей оценки района.</p>
    {loading && <p role="status" className="mt-5 text-sm text-[#647f80]">Сопоставляем районы с анкетой…</p>}
    {error && <p role="alert" className="mt-5 text-sm text-[#a15c49]">{error}. Попробуйте позже.</p>}
    {items?.length === 0 && <p className="mt-5 text-sm text-[#647f80]">Пока нет районов с достаточными данными для подбора.</p>}
    {!!items?.length && <div className="mt-6 grid gap-3 md:grid-cols-2">{items.map((item) => <article key={item.district_id} className="rounded-[20px] bg-[#f1f8f5] p-5">
      <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-bold text-[#168e79]">№ {item.rank}</p><h3 className="mt-1 font-semibold">{item.district_name}</h3></div><span className="text-2xl font-bold text-[#168e79]">{Math.round(item.match_score)}<span className="text-sm">/100</span></span></div>
      {item.reasons.length > 0 && <p className="mt-3 text-sm leading-relaxed text-[#547477]">{item.reasons[0]}</p>}
      <Link href={`/district?districtId=${item.district_id}`} className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-[#0d766c]">Посмотреть на карте <ArrowRight size={15} /></Link>
    </article>)}</div>}
  </section>;
}
