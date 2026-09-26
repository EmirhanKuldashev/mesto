"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Compass } from "lucide-react";
import { AnalyticsScore } from "@/components/analytics-score";
import { RecommendationPanel } from "@/components/recommendation-panel";
import { Brand, EmptyState } from "@/components/concept-ui";
import { CianListingCard } from "@/components/cian-listing-card";
import { useAnalytics } from "@/lib/analytics-store";
import { useCianListings } from "@/lib/cian-listings";
import { useOnboarding } from "@/lib/onboarding-store";

export default function ResultsPage() {
  const profileId = useOnboarding((state) => state.profileId);
  const { status, scores, error, load } = useAnalytics();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [flowWarning, setFlowWarning] = useState<string | null>(null);
  const { listings, loading: listingsLoading, error: listingsError } = useCianListings();

  useEffect(() => { void load(profileId); }, [load, profileId]);
  useEffect(() => { const warning = sessionStorage.getItem("mesto-save-status"); setFlowWarning(warning && profileId ? warning : null); if (warning && profileId) sessionStorage.removeItem("mesto-save-status"); }, [profileId]);
  const selected = scores.find((item) => item.district.id === selectedId) ?? scores[0];

  return <main className="page-shell">
    <header className="content-shell flex h-20 items-center justify-between"><Brand /><Link href="/onboarding" className="text-sm text-[#b4cece] hover:text-white">Изменить ответы</Link></header>
    <section className="mesh-background border-t border-white/10"><div className="content-shell py-14 sm:py-20">
      <p className="eyebrow">Персональная аналитика · Красноярск</p>
      <h1 className="mt-5 max-w-4xl text-[clamp(3rem,6vw,6rem)] font-semibold leading-none tracking-[-.07em]">Ваш <span className="gradient-text">MESTO Score.</span></h1>
      <p className="mt-5 max-w-2xl text-sm leading-relaxed text-[#acc8ca]">Оценка района по доступным данным, вашим приоритетам и известным планам развития.</p>
      <div className="mt-8 flex flex-wrap gap-3"><Link href="/district" className="primary-button"><Compass size={17} /> Открыть карту</Link><Link href="/onboarding" className="secondary-button"><ArrowLeft size={17} /> К анкете</Link></div>
    </div></section>
    <section className="bg-[#f2f8f5] py-12 sm:py-16"><div className="content-shell">
      {(status === "loading" || status === "idle") && <p role="status" className="text-[#54787a]">Получаем анализ районов…</p>}
      {flowWarning && <p role="alert" className="mb-6 rounded-[20px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]">{flowWarning}</p>}
      {status === "demo" && <div role="status" className="mb-6 rounded-[20px] border border-[#eac998] bg-[#fff5e5] p-5 text-sm text-[#76562b]"><strong>Demo mode.</strong> {error ? `Не удалось получить анализ: ${error}. Показан демонстрационный пример.` : "Сохраните анкету с согласием, чтобы увидеть персональный результат. Сейчас показан демонстрационный пример."} {profileId && <button type="button" onClick={() => void load(profileId, true)} className="ml-2 font-semibold underline">Повторить запрос</button>}</div>}
      {status === "empty" && <EmptyState title="Районов для анализа пока нет" body="Проверьте, что данные районов загружены в backend, и повторите запрос." />}
      {(status === "ready" || status === "demo") && selected && <>
        {scores.length > 1 && <div className="mb-6 flex flex-wrap gap-2" aria-label="Выбор района">{scores.map((item) => <button key={item.district.id} type="button" onClick={() => setSelectedId(item.district.id)} aria-pressed={selected.district.id === item.district.id} className={`rounded-full px-5 py-3 text-sm font-semibold transition ${selected.district.id === item.district.id ? "bg-[#0d766c] text-white" : "bg-white text-[#41686a] hover:bg-[#e1f0e8]"}`}>{item.district.name} · {item.score === null ? "—" : Math.round(item.score)}</button>)}</div>}
        <AnalyticsScore score={selected} />
        {status === "ready" && profileId && <RecommendationPanel key={profileId} profileId={profileId} />}
        {status === "ready" && <Link href={`/district?districtId=${selected.district.id}`} className="mt-7 inline-flex items-center gap-2 font-semibold text-[#0a786d]">Посмотреть район на карте <Compass size={17} /></Link>}
      </>}
    </div></section>
    <section className="content-shell py-14"><h2 className="section-title">Объявления жилья</h2><p className="mt-3 max-w-2xl text-sm text-[#a3bfc0]">Загруженные предложения ЦИАН показаны отдельно от оценки района.</p>
      {listingsLoading && <p role="status" className="mt-8">Загружаем объявления…</p>}
      {listingsError && <p role="alert" className="mt-8 text-[#ffbaa8]">Не удалось загрузить объявления: {listingsError}</p>}
      {!listingsLoading && !listingsError && !listings.length && <p className="mt-8 text-[#a3bfc0]">Объявлений пока нет.</p>}
      {!!listings.length && <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[...listings].sort((a, b) => a.price - b.price).map((item) => <CianListingCard key={item.id} listing={item} />)}</div>}
    </section>
  </main>;
}
