"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Compass } from "lucide-react";
import { AnalyticsScore } from "@/components/analytics-score";
import { RecommendationPanel } from "@/components/recommendation-panel";
import { Brand, EmptyState, Skeleton } from "@/components/concept-ui";
import { CianListingCard } from "@/components/cian-listing-card";
import { useAnalytics } from "@/lib/analytics-store";
import { useCianListings } from "@/lib/cian-listings";
import { useOnboarding } from "@/lib/onboarding-store";
import { useOnboardingReady } from "@/lib/use-onboarding-ready";

export default function ResultsPage() {
  const ready = useOnboardingReady();
  const profileId = useOnboarding((state) => state.profileId);
  const draft = useOnboarding((state) => state.draft);
  const { status, scores, recommendations, recommendationError, error, load } = useAnalytics();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [flowWarning, setFlowWarning] = useState<string | null>(null);
  const { listings, loading: listingsLoading, error: listingsError } = useCianListings();

  useEffect(() => { if (ready) void load(profileId); }, [ready, load, profileId]);
  useEffect(() => {
    if (!ready || !profileId) return;
    const warning = sessionStorage.getItem("mesto-save-status");
    if (warning) { setFlowWarning(warning); sessionStorage.removeItem("mesto-save-status"); }
  }, [ready, profileId]);

  const rankedId = recommendations[0]?.district_id;
  const selected = scores.find((item) => item.district.id === selectedId) ??
    scores.find((item) => item.district.id === rankedId) ?? scores[0];
  const selectedRecommendation = recommendations.find((item) => item.district_id === selected?.district.id);
  const matchingHousing = status === "ready" && selected && draft.housing_goal !== "rent" ? listings.filter((item) =>
    item.district_id === selected.district.id &&
    (draft.purchase_budget <= 0 || item.price <= draft.purchase_budget)) : [];

  return <main className="page-shell">
    <header className="content-shell flex h-20 items-center justify-between"><Brand /><Link href="/onboarding" className="text-sm text-[#b4cece] hover:text-white">Изменить ответы</Link></header>
    <section className="mesh-background border-t border-white/10"><div className="content-shell py-14 sm:py-20">
      <p className="eyebrow">Персональная аналитика · Красноярск</p>
      <h1 className="mt-5 max-w-4xl text-[clamp(3rem,6vw,6rem)] font-semibold leading-none tracking-[-.07em]">Ваши <span className="gradient-text">лучшие места.</span></h1>
      <p className="mt-5 max-w-2xl text-sm leading-relaxed text-[#acc8ca]">Рекомендации по вашему сценарию и объяснимая оценка района по доступным данным.</p>
      <div className="mt-8 flex flex-wrap gap-3"><Link href={selected ? `/district?districtId=${selected.district.id}` : "/district"} className="primary-button"><Compass size={17} /> Открыть карту</Link><Link href="/onboarding" className="secondary-button"><ArrowLeft size={17} /> К сценарию</Link></div>
    </div></section>
    <section className="bg-[#f2f8f5] py-12 sm:py-16"><div className="content-shell space-y-7">
      {(!ready || status === "loading" || status === "idle") && <div role="status" className="space-y-4 text-[#54787a]"><p>{ready ? "Получаем персональный анализ и рекомендации…" : "Восстанавливаем ваш сценарий…"}</p><Skeleton className="h-40 w-full" /></div>}
      {flowWarning && <p role="alert" className="rounded-[20px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]">{flowWarning}</p>}
      {status === "needs_profile" && <div role="status" className="rounded-[20px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]">Для персонального анализа заполните анкету и дайте согласие на обработку данных. <Link href="/onboarding" className="ml-2 font-semibold underline">Создать сценарий</Link></div>}
      {status === "error" && <div role="alert" className="rounded-[20px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]">Не удалось получить анализ{error ? `: ${error}` : "."} <button type="button" onClick={() => void load(profileId, true)} className="ml-2 font-semibold underline">Повторить запрос</button></div>}
      {status === "empty" && <EmptyState title="Пока нет районов для анализа" body="Данные районов обновляются. Пожалуйста, вернитесь позже." />}
      {status === "ready" && <RecommendationPanel items={recommendations} error={recommendationError} selectedId={selected?.district.id ?? null} onSelect={setSelectedId} onRetry={() => void load(profileId, true)} />}
      {status === "ready" && selected && <>
        {recommendations.length === 0 && scores.length > 1 && <div className="flex flex-wrap gap-2" aria-label="Выбор района">{scores.map((item) => <button key={item.district.id} type="button" onClick={() => setSelectedId(item.district.id)} aria-pressed={selected.district.id === item.district.id} className={`rounded-full px-5 py-3 text-sm font-semibold transition ${selected.district.id === item.district.id ? "bg-[#0d766c] text-white" : "bg-white text-[#41686a] hover:bg-[#e1f0e8]"}`}>{item.district.name} · {item.score === null ? "—" : Math.round(item.score)}</button>)}</div>}
        <div><h2 className="mb-3 text-2xl font-semibold text-[#153c44]">{selected.district.name}</h2>{selectedRecommendation && <p className="mb-5 text-sm text-[#547477]">Ваш Match Score: {Math.round(selectedRecommendation.match_score)}%. Оценка района и причины расчёта ниже.</p>}<AnalyticsScore score={selected} /></div>
        {status === "ready" && <Link href={`/district?districtId=${selected.district.id}`} className="inline-flex items-center gap-2 font-semibold text-[#0a786d]">Посмотреть район на карте <Compass size={17} /></Link>}
      </>}
    </div></section>
    <section className="content-shell py-14"><h2 className="section-title">Жильё в выбранном районе</h2>
      <p className="mt-3 max-w-2xl text-sm text-[#a3bfc0]">Показываем только предложения из базы с привязкой к району и в пределах указанного бюджета. Совместимость отдельного объекта пока не рассчитывается.</p>
      {listingsLoading && <p role="status" className="mt-8">Загружаем предложения…</p>}
      {listingsError && <p role="alert" className="mt-8 text-[#ffbaa8]">Не удалось загрузить предложения: {listingsError}</p>}
      {!listingsLoading && !listingsError && status === "ready" && draft.housing_goal === "rent" && <p className="mt-8 text-[#a3bfc0]">Для аренды в этом каталоге пока нет привязанных предложений.</p>}
      {!listingsLoading && !listingsError && status === "ready" && draft.housing_goal !== "rent" && matchingHousing.length === 0 && <p className="mt-8 text-[#a3bfc0]">Для выбранного района и бюджета привязанных предложений пока нет.</p>}
      {matchingHousing.length > 0 && <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[...matchingHousing].sort((a, b) => a.price - b.price).map((item) => <CianListingCard key={item.id} listing={item} />)}</div>}
      {listings.length > 0 && <details className="mt-10"><summary className="cursor-pointer text-sm font-semibold text-[#9ce9d2]">Все загруженные объявления ({listings.length})</summary><div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[...listings].sort((a, b) => a.price - b.price).map((item) => <CianListingCard key={item.id} listing={item} />)}</div></details>}
    </section>
  </main>;
}
