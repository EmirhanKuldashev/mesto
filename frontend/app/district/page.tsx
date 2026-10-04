"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, MapPin } from "lucide-react";
import type { MapLayer } from "@/components/district-map";
import { AnalyticsScore } from "@/components/analytics-score";
import { DistrictMarket } from "@/components/district-market";
import { Brand, EmptyState, Skeleton } from "@/components/concept-ui";
import { useAnalytics } from "@/lib/analytics-store";
import { useComplexData } from "@/lib/complex-data";
import { scoreColor, scoreComplex, scoreDistricts, type ScoredDistrict } from "@/lib/complex-scoring";
import { useOnboarding } from "@/lib/onboarding-store";
import { useOnboardingReady } from "@/lib/use-onboarding-ready";

const layerOptions: { key: MapLayer; label: string }[] = [
  { key: "housing", label: "🏠 Жильё" }, { key: "schools", label: "🏫 Школы" },
  { key: "kindergarten", label: "🎓 Детские сады" }, { key: "healthcare", label: "🏥 Медицина" },
  { key: "transport", label: "🚌 Транспорт" }, { key: "parks", label: "🌳 Парки" },
  { key: "future", label: "🚧 Будущие объекты" },
];

const DistrictMap = dynamic(() => import("@/components/district-map"), { ssr: false,
  loading: () => <Skeleton className="h-[580px] w-full bg-[#dbeae5]" /> });

export default function DistrictPage() {
  const ready = useOnboardingReady();
  const draft = useOnboarding((state) => state.draft);
  const profileId = useOnboarding((state) => state.profileId);
  const { status, scores, error: analyticsError, load } = useAnalytics();
  const { complexes, pois, districts, futureObjects, loading: mapLoading, error: mapError } = useComplexData();
  const [layers, setLayers] = useState<Record<MapLayer, boolean>>({ housing: true, schools: true, kindergarten: true, healthcare: true, transport: true, parks: true, future: true });
  const [selectedDistrictId, setSelectedDistrictId] = useState<number | null>(null);

  useEffect(() => { if (ready) void load(profileId); }, [ready, load, profileId]);
  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get("districtId"));
    if (Number.isInteger(id) && id > 0) setSelectedDistrictId(id);
  }, []);

  const complexDistricts = useMemo(() => {
    const scored = complexes.map((complex) => ({ ...complex, score: scoreComplex(complex, pois, draft) }));
    return scoreDistricts(districts, scored);
  }, [complexes, pois, districts, draft]);
  const real = status === "ready";
  const mapDistricts: ScoredDistrict[] = useMemo(() => districts.map((district) => {
    const score = scores.find((item) => item.district.id === district.id);
    return { ...district, value: score?.score === null || score === undefined ? null : score.score / 100,
      coverage: score?.confidence ?? 0, complexes: complexDistricts.find((item) => item.id === district.id)?.complexes ?? [] };
  }), [districts, scores, complexDistricts]);
  const selectedScore = real ? scores.find((item) => item.district.id === selectedDistrictId) : undefined;
  const displayedScores = real ? scores : [];
  const selectedMapDistrict = mapDistricts.find((item) => item.id === selectedDistrictId);
  const selectedValue = selectedMapDistrict?.value ?? (real && selectedScore?.score != null ? selectedScore.score / 100 : null);

  return <main className="page-shell">
    <header className="content-shell flex h-20 items-center justify-between"><Brand /><Link href="/results" className="text-sm text-[#abc6c7]">К результатам</Link></header>
    <section className="border-t border-white/10 bg-[#092030]"><div className="content-shell py-12 sm:py-16">
      <Link href="/results" className="inline-flex items-center gap-2 text-xs font-semibold text-[#91cfc1]"><ArrowLeft size={15} /> К результатам</Link>
      <p className="eyebrow mt-8">Районы · Красноярск</p>
      <h1 className="mt-4 text-[clamp(2.8rem,6vw,5.8rem)] font-semibold leading-none tracking-[-.07em]">Город и ваши <span className="gradient-text">приоритеты.</span></h1>
      <p className="mt-5 max-w-3xl text-sm leading-relaxed text-[#a8c3c4]">Выберите район на карте или в списке, чтобы увидеть его MESTO Score, причины и потенциал развития.</p>
    </div></section>
    <section className="bg-[#f0f7f3] py-8 text-[#14333e] sm:py-12"><div className="content-shell grid gap-6 lg:grid-cols-[300px_1fr]">
      <aside className="space-y-5">
        {status === "needs_profile" && <div role="status" className="rounded-[22px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]">Заполните анкету, чтобы получить MESTO Score и персональный Match. <Link href="/onboarding" className="font-semibold underline">Создать сценарий</Link></div>}
        {status === "error" && <div role="alert" className="rounded-[22px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]">Не удалось получить оценку{analyticsError ? `: ${analyticsError}` : "."} <button type="button" onClick={() => void load(profileId, true)} className="mt-2 block font-semibold underline">Повторить запрос</button></div>}
        <div className="rounded-[26px] border border-[#dbe8e4] bg-white p-6">
          <h2 className="text-xl font-semibold">{selectedMapDistrict?.name ?? selectedScore?.district.name ?? "MESTO Score районов"}</h2>
          <div className="mt-4 flex items-center gap-3"><span className="h-8 w-8 rounded-full" style={{ backgroundColor: scoreColor(selectedValue) }} /><span className="text-3xl font-semibold">{selectedValue === null ? "—" : real ? `${Math.round(selectedValue * 100)}/100` : `${Math.round(selectedValue * 100)}%`}</span></div>
          <p className="mt-3 text-sm text-[#607f82]">{real ? "Оценка района по Analytics API" : "Ожидаем результат анализа"}</p>
          {selectedDistrictId !== null && <button type="button" onClick={() => setSelectedDistrictId(null)} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-[#138d7b]"><ArrowLeft size={15} /> Показать весь город</button>}
          <div className="mt-6 space-y-2 text-sm">{[["0–39", .2], ["40–69", .55], ["70–100", .85], ["Нет оценки", null]].map(([label, value]) => <div key={String(label)} className="flex items-center gap-3"><span className="h-4 w-4 rounded-full" style={{ backgroundColor: scoreColor(value as number | null) }} />{label}</div>)}</div>
        </div>
        <div className="rounded-[26px] border border-[#dbe8e4] bg-white p-6"><h3 className="font-semibold">Районы Красноярска</h3>
          {real ? <div className="mt-4 space-y-2">{displayedScores.map((item) => <button key={item.district.id} type="button" onClick={() => setSelectedDistrictId(item.district.id)} aria-pressed={selectedDistrictId === item.district.id} className={`flex w-full items-center justify-between rounded-xl border px-3 py-3 text-left text-sm ${selectedDistrictId === item.district.id ? "border-[#2ab993] bg-[#e9f8f2]" : "border-[#e1ebe7] hover:bg-[#f3faf7]"}`}><span>{item.district.name}</span><span className="font-semibold">{item.score === null ? "—" : Math.round(item.score)}</span></button>)}</div> : <p className="mt-3 text-sm text-[#789295]">{status === "loading" ? "Получаем оценку районов…" : "Для оценки пройдите анкету"}</p>}
        </div>
        {draft.life_points.length > 0 && <div className="rounded-[26px] border border-[#dbe8e4] bg-white p-6"><h3 className="font-semibold">Ваши точки жизни</h3><ul className="mt-4 space-y-2">{draft.life_points.map((point) => <li key={point.localId} className="flex items-start gap-2 text-sm text-[#607f82]"><MapPin size={15} className="mt-0.5 text-[#187dda]" />{point.name}</li>)}</ul></div>}
        <Link href="/onboarding" className="text-sm font-semibold text-[#138d7b]">Изменить анкету</Link>
      </aside>
      <div>{mapLoading && <p role="status" className="mb-3 text-sm">Загружаем карту районов…</p>}{mapError && <p role="alert" className="mb-3 text-sm text-[#a15c49]">Не удалось загрузить геоданные: {mapError}</p>}
        <div className="mb-4 flex flex-wrap gap-2" aria-label="Слои карты">{layerOptions.map((layer) =>
          <button key={layer.key} type="button" aria-pressed={layers[layer.key]} onClick={() => setLayers((current) => ({ ...current, [layer.key]: !current[layer.key] }))}
            className={`rounded-full border px-3 py-2 text-xs font-semibold transition ${layers[layer.key] ? "border-[#279f83] bg-[#dcf5e9] text-[#0d766c]" : "border-[#cadbd5] bg-white text-[#63827f]"}`}>{layer.label}</button>)}</div>
        {selectedDistrictId !== null && !selectedMapDistrict && <p role="status" className="mb-3 rounded-xl bg-white p-4 text-sm text-[#607f82]">Для этого района в базе нет подтверждённой геометрии карты. Оценка и сигналы доступны ниже, объекты на карте не привязываются произвольно.</p>}
        <DistrictMap points={draft.life_points} districts={mapDistricts} pois={pois} futureObjects={futureObjects} layers={layers} selectedDistrictId={selectedMapDistrict?.id ?? null} onSelectDistrict={setSelectedDistrictId} />
        <p className="mt-3 text-xs text-[#6c898c]">Картографическая подложка и границы: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="underline">? OpenStreetMap contributors ? ODbL</a>. Серый район не имеет оценки.</p>
      </div>
    </div></section>
    <section className="bg-[#f2f8f5] py-14"><div className="content-shell">
      <h2 className="mb-7 text-3xl font-semibold tracking-[-.05em] text-[#14333e]">{selectedDistrictId === null ? "Выберите район" : selectedScore?.district.name ?? "Оценка района"}</h2>
      {(status === "idle" || status === "loading") && <p role="status" className="text-[#607f82]">Получаем MESTO Score…</p>}
      {status === "empty" && <EmptyState title="Районов для анализа пока нет" body="Данные районов ещё не загружены в backend." />}
      {real && selectedDistrictId === null && <p className="text-[#607f82]">Нажмите на район в списке или на карте.</p>}
      {real && selectedDistrictId !== null && !selectedScore && <EmptyState title="Для этого района нет оценки" body="Выберите другой район из списка." />}
      {(real && selectedDistrictId !== null) && selectedScore && <AnalyticsScore score={selectedScore} />}
      {(selectedMapDistrict || selectedScore) && <DistrictMarket districtId={selectedMapDistrict?.id ?? selectedScore!.district.id} profileId={profileId} />}
      {selectedMapDistrict && selectedMapDistrict.complexes.length > 0 && <div className="mt-8 rounded-[26px] border border-[#dbe8e4] bg-white p-6 text-[#153c44]">
        <h3 className="text-xl font-semibold">Жилые комплексы района</h3><p className="mt-2 text-sm text-[#607f82]">Объекты из API ЦИАН. Локальная оценка ЖК отличается от MESTO Score района.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">{selectedMapDistrict.complexes.map((complex) => <article key={complex.id} className="rounded-xl bg-[#f1f8f5] p-4"><h4 className="font-semibold">{complex.name}</h4><p className="mt-1 text-sm text-[#607f82]">Цена от: {complex.price_from ? `${new Intl.NumberFormat("ru-RU").format(complex.price_from)} ₽` : "не указана"}</p><p className="mt-1 text-sm text-[#607f82]">Соответствие сценарию: {complex.score.value === null ? "нет данных" : `${Math.round(complex.score.value * 100)}%`}</p><p className="mt-1 text-xs text-[#789295]">{complex.score.reasons.slice(0, 2).join(" · ")}</p></article>)}</div>
      </div>}
    </div></section>
  </main>;
}
