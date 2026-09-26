"use client";

import Link from "next/link";
import { ArrowLeft, Compass, Database, Home, Wallet } from "lucide-react";
import { Brand, EmptyState, MetricTile } from "@/components/concept-ui";
import { CianListingCard } from "@/components/cian-listing-card";
import { formatPrice, useCianListings } from "@/lib/cian-listings";

export default function ResultsPage() {
  const { listings, loading, error } = useCianListings();
  const sorted = [...listings].sort((a, b) => a.price - b.price);
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)].price : null;
  const fetchedAt = listings.reduce((latest, item) => item.fetched_at > latest ? item.fetched_at : latest, "");

  return <main className="page-shell">
    <header className="content-shell flex h-20 items-center justify-between"><Brand /><Link href="/onboarding" className="text-sm text-[#b4cece] hover:text-white">Изменить ответы</Link></header>
    <section className="mesh-background border-t border-white/10"><div className="content-shell py-16 sm:py-24">
      <p className="eyebrow">Объявления ЦИАН · Красноярск</p>
      <h1 className="mt-5 max-w-4xl text-[clamp(3rem,6vw,6rem)] font-semibold leading-none tracking-[-.07em]">Реальные квартиры <span className="gradient-text">в одном списке.</span></h1>
      <p className="mt-6 max-w-2xl text-base leading-relaxed text-[#acc8ca]">Цены и параметры взяты из сохранённых объявлений ЦИАН. Рейтинг районов и персональный подбор пока не рассчитываются.</p>
      <div className="mt-9 flex flex-wrap gap-3"><Link href="/district" className="primary-button"><Compass size={17} /> Открыть карту</Link><Link href="/onboarding" className="secondary-button"><ArrowLeft size={17} /> К анкете</Link></div>
    </div></section>
    <section className="bg-[#f2f8f5] py-14 text-[#12313d] sm:py-20"><div className="content-shell">
      <div className="grid gap-3 sm:grid-cols-3"><MetricTile label="Объявлений" value={loading ? "…" : String(listings.length)} note="Источник: ЦИАН" icon={Home} /><MetricTile label="Минимальная цена" value={sorted.length ? formatPrice(sorted[0].price) : "—"} note="Среди загруженных объявлений" icon={Wallet} /><MetricTile label="Медианная цена" value={median !== null ? formatPrice(median) : "—"} note="Среди загруженных объявлений" icon={Database} /></div>
      <h2 className="mt-14 text-3xl font-semibold tracking-[-.05em]">Объявления</h2>
      {fetchedAt && <p className="mt-2 text-sm text-[#607f82]">Данные собраны {new Date(fetchedAt).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" })}</p>}
      {loading && <p role="status" className="mt-8 text-[#607f82]">Загружаем объявления…</p>}
      {error && <div role="alert" className="mt-8"><EmptyState title="Данные недоступны" body={`${error}. Проверьте подключение к backend.`} /></div>}
      {!loading && !error && listings.length === 0 && <div className="mt-8"><EmptyState title="Объявлений пока нет" body="Загрузите RAW JSON ЦИАН через backend/data/loaders/cian_loader.py." /></div>}
      {listings.length > 0 && <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{sorted.map((listing) => <CianListingCard key={listing.id} listing={listing} />)}</div>}
      <p className="mt-9 text-xs leading-relaxed text-[#78918f]">Объявления могут устареть. Уточняйте цену и доступность на странице источника. У объявлений нет проверенных координат, поэтому они не отображаются маркерами на карте.</p>
    </div></section>
  </main>;
}
