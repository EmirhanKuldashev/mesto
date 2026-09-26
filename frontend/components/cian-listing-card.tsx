import { ArrowUpRight, MapPin } from "lucide-react";
import { type CianListing, formatArea, formatPrice } from "@/lib/cian-listings";

export function CianListingCard({ listing }: { listing: CianListing }) {
  return <article className="rounded-[26px] border border-[#dce9e5] bg-white p-6 text-[#173644] shadow-[0_16px_40px_rgba(4,39,49,0.06)]">
    <p className="text-[11px] font-bold uppercase tracking-[.17em] text-[#168e78]">ЦИАН · объявление {listing.external_id}</p>
    <h3 className="mt-3 min-h-14 text-xl font-semibold tracking-[-.04em]">{listing.title || "Название не указано"}</h3>
    <p className="mt-3 text-2xl font-semibold">{formatPrice(listing.price)}</p>
    <p className="mt-1 text-sm text-[#54747b]">{formatArea(listing.area_sqm)}{listing.rooms !== null ? ` · ${listing.rooms}-комн.` : ""}{listing.floor !== null ? ` · ${listing.floor} этаж` : ""}</p>
    <p className="mt-4 flex min-h-10 items-start gap-2 text-sm text-[#607f82]"><MapPin size={16} className="mt-0.5 shrink-0" />{listing.address || listing.city || "Адрес не указан"}</p>
    <a href={listing.url} target="_blank" rel="noopener noreferrer" className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-[#138d79] hover:underline">Открыть на ЦИАН <ArrowUpRight size={16} /></a>
  </article>;
}
