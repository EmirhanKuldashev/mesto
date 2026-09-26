"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, MapPin } from "lucide-react";
import { Brand, EmptyState, Skeleton } from "@/components/concept-ui";
import { useComplexData } from "@/lib/complex-data";
import { scoreColor, scoreComplex, scoreDistricts } from "@/lib/complex-scoring";
import { formatPrice } from "@/lib/cian-listings";
import { useOnboarding } from "@/lib/onboarding-store";

const DistrictMap = dynamic(() => import("@/components/district-map"), { ssr: false, loading: () => <Skeleton className="h-[580px] w-full bg-[#dbeae5]" /> });

export default function DistrictPage() {
  const draft = useOnboarding((state) => state.draft);
  const { complexes, pois, districts, loading, error } = useComplexData();
  const [selectedDistrictId, setSelectedDistrictId] = useState<number | null>(null);
  const scored = useMemo(() => complexes.map((complex) => ({ ...complex, score: scoreComplex(complex, pois, draft) })), [complexes, pois, draft]);
  const districtScores = useMemo(() => scoreDistricts(districts, scored), [districts, scored]);
  const selectedDistrict = districtScores.find((district) => district.id === selectedDistrictId) ?? null;
  const located = scored.filter((complex) => complex.location).length;
  const cityScores = scored.map((complex) => complex.score.value).filter((value): value is number => value !== null);
  const cityValue = cityScores.length ? cityScores.reduce((total, value) => total + value, 0) / cityScores.length : null;
  const displayedValue = selectedDistrict ? selectedDistrict.value : cityValue;
  const ranked = selectedDistrict ? [...selectedDistrict.complexes].sort((a, b) => (b.score.value ?? -1) - (a.score.value ?? -1)) : [];

  return <main className="page-shell">
    <header className="content-shell flex h-20 items-center justify-between"><Brand /><Link href="/results" className="text-sm text-[#abc6c7]">К объявлениям</Link></header>
    <section className="border-t border-white/10 bg-[#092030]"><div className="content-shell py-12 sm:py-16">
      <Link href="/results" className="inline-flex items-center gap-2 text-xs font-semibold text-[#91cfc1]"><ArrowLeft size={15} /> К объявлениям</Link>
      <p className="eyebrow mt-8">Административные районы · Красноярск</p>
      <h1 className="mt-4 text-[clamp(2.8rem,6vw,5.8rem)] font-semibold leading-none tracking-[-.07em]">Город и ваши <span className="gradient-text">приоритеты.</span></h1>
      <p className="mt-5 max-w-3xl text-sm leading-relaxed text-[#a8c3c4]">Общий вид показывает среднее соответствие ЖК внутри каждого административного района. Выберите район на карте или в списке, чтобы увидеть оценки отдельных ЖК. Границы районов получены из OpenStreetMap; ЖК — из ЦИАН.</p>
      <p className="mt-3 max-w-3xl text-xs leading-relaxed text-[#8caaad]">Цвет от красного к зелёному соответствует оценке от 0 до 1. Серый означает, что оценки нет. Близость инфраструктуры считается по прямой, поэтому фактическое время пути может отличаться.</p>
    </div></section>
    <section className="bg-[#f0f7f3] py-8 text-[#14333e] sm:py-12"><div className="content-shell grid gap-6 lg:grid-cols-[300px_1fr]">
      <aside className="space-y-5">
        <div className="rounded-[26px] border border-[#dbe8e4] bg-white p-6">
          <h2 className="text-xl font-semibold">{selectedDistrict ? `${selectedDistrict.name} район` : "Температура города"}</h2>
          <div className="mt-4 flex items-center gap-3"><span className="h-8 w-8 rounded-full" style={{ backgroundColor: scoreColor(displayedValue) }} /><span className="text-3xl font-semibold">{displayedValue?.toFixed(2) ?? "Нет оценки"}</span></div>
          <p className="mt-3 text-sm text-[#607f82]">{selectedDistrict ? `Среднее по ${selectedDistrict.complexes.length} ЖК района` : `Среднее по ${cityScores.length} оценённым ЖК города`}</p>
          <p className="mt-1 text-sm text-[#607f82]">Административных районов: {loading ? "…" : districtScores.length}</p>
          <p className="mt-1 text-sm text-[#607f82]">ЖК: {loading ? "…" : complexes.length} · с координатами: {loading ? "…" : located}</p>
          <p className="mt-1 text-sm text-[#607f82]">Объектов инфраструктуры OSM: {loading ? "…" : pois.length}</p>
          {selectedDistrict && <button type="button" onClick={() => setSelectedDistrictId(null)} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-[#138d7b]"><ArrowLeft size={15} /> Показать весь город</button>}
          <div className="mt-6 space-y-2 text-sm">{[["0–0,39", .2], ["0,4–0,69", .55], ["0,7–1", .85], ["Нет оценки", null]].map(([label, value]) => <div key={String(label)} className="flex items-center gap-3"><span className="h-4 w-4 rounded-full" style={{ backgroundColor: scoreColor(value as number | null) }} />{label}</div>)}</div>
          <p className="mt-6 text-xs leading-relaxed text-[#789295]">Район окрашен по среднему скорингу ЖК, а в выбранном районе каждый ЖК имеет собственную оценку. Покрытие показывает, для какой доли выбранных критериев доступны данные.</p>
        </div>
        <div className="rounded-[26px] border border-[#dbe8e4] bg-white p-6"><h3 className="font-semibold">Районы Красноярска</h3>
          {districtScores.length ? <div className="mt-4 space-y-2">{districtScores.map((district) => <button key={district.id} type="button" onClick={() => setSelectedDistrictId(district.id)} aria-pressed={selectedDistrictId === district.id} className={`flex w-full items-center justify-between rounded-xl border px-3 py-3 text-left text-sm ${selectedDistrictId === district.id ? "border-[#2ab993] bg-[#e9f8f2]" : "border-[#e1ebe7] hover:bg-[#f3faf7]"}`}><span>{district.name}<span className="ml-1 text-xs text-[#789295]">({district.complexes.length})</span></span><span className="rounded-full px-2 py-1 text-xs font-semibold text-[#102b35]" style={{ backgroundColor: scoreColor(district.value) }}>{district.value?.toFixed(2) ?? "—"}</span></button>)}</div> : !loading && <p className="mt-3 text-sm text-[#789295]">Административные границы ещё не загружены.</p>}
        </div>
        {draft.life_points.length ? <div className="rounded-[26px] border border-[#dbe8e4] bg-white p-6"><h3 className="font-semibold">Ваши точки жизни</h3><ul className="mt-4 space-y-2">{draft.life_points.map((point) => <li key={point.localId} className="flex items-start gap-2 text-sm text-[#607f82]"><MapPin size={15} className="mt-0.5 text-[#187dda]" />{point.name}</li>)}</ul></div> : <EmptyState title="Точки жизни не указаны" body="Добавьте их в анкете для более полного скоринга." />}
        <Link href="/onboarding" className="inline-flex items-center gap-2 text-sm font-semibold text-[#138d7b]">Изменить анкету <ArrowRight size={16} /></Link>
      </aside>
      <div><DistrictMap points={draft.life_points} districts={districtScores} selectedDistrictId={selectedDistrict?.id ?? null} onSelectDistrict={setSelectedDistrictId} /><p className="mt-3 text-xs text-[#6c898c]">Подложка, границы и инфраструктура: © OpenStreetMap contributors. ЖК: ЦИАН. Серый район не имеет рассчитанного соответствия.</p></div>
    </div></section>
    <section className="content-shell py-16">
      <h2 className="section-title">{selectedDistrict ? `ЖК: ${selectedDistrict.name} район` : "Выберите район"}</h2>
      <p className="mt-3 max-w-3xl text-sm text-[#a3bfc0]">{selectedDistrict ? "Здесь видны оценки отдельных ЖК выбранного административного района. Оценка от 0 до 1 показывает соответствие доступным данным и вашим ответам, а не качество самого ЖК." : "На общем виде карта окрашена по средним оценкам районов. Выберите район, чтобы увидеть распределение по ЖК."}</p>
      {loading && <p role="status" className="mt-8">Загружаем районы, ЖК и инфраструктуру…</p>}
      {error && <p role="alert" className="mt-8 text-[#ffbaa8]">Не удалось загрузить данные: {error}</p>}
      {!loading && !error && !districtScores.length && <p className="mt-8">Границы районов не загружены. Запустите loader OSM для административных районов.</p>}
      {selectedDistrict && !ranked.length && <p className="mt-8">В этом районе нет загруженных ЖК ЦИАН.</p>}
      {!!ranked.length && <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{ranked.map((complex) => <article key={complex.id} className="rounded-[24px] border border-white/10 bg-white/[.07] p-6">
        <div className="flex items-start justify-between gap-3"><h3 className="text-lg font-semibold">{complex.name}</h3><span className="shrink-0 rounded-full px-3 py-1 text-xs font-bold text-[#102b35]" style={{ backgroundColor: scoreColor(complex.score.value) }}>{complex.score.value === null ? "Нет оценки" : complex.score.value.toFixed(2)}</span></div>
        <p className="mt-3 text-sm text-[#a3c0c0]">Цена от: {complex.price_from ? formatPrice(complex.price_from) : "не указана"}</p><p className="mt-1 text-xs text-[#85a5a7]">Покрытие: {Math.round(complex.score.coverage * 100)}%</p>
        {complex.score.reasons.length > 0 && <p className="mt-3 text-xs text-[#90b2b3]">{complex.score.reasons.slice(0, 3).join(" · ")}</p>}
        {complex.url && <a href={complex.url} target="_blank" rel="noopener noreferrer" className="mt-5 inline-block text-sm font-semibold text-[#9de9d3] hover:underline">Открыть на ЦИАН ↗</a>}
      </article>)}</div>}
    </section>
  </main>;
}
