"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { Check, Compass, MapPin } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return <Link href="/" className="focus-outline inline-flex items-center gap-3 font-semibold tracking-[-0.06em] text-white" aria-label="МЕСТО — главная">
    <span className="grid h-10 w-10 place-items-center rounded-[15px] border border-[#9ef5d9]/30 bg-[#9ef5d9]/15 text-[#a8f7df]"><MapPin size={20} strokeWidth={2.4} /></span>
    {!compact && <span className="text-[25px]">МЕСТО<span className="ml-1 text-[#9ef5d9]">.</span></span>}
  </Link>;
}

export function Reveal({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const reduced = useReducedMotion();
  return <motion.div className={className} initial={reduced ? false : { opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: "-60px" }} transition={{ duration: .65, ease: [0.22, 1, 0.36, 1], delay: reduced ? 0 : delay }}>{children}</motion.div>;
}

export function SelectionCard({ title, description, icon: Icon, selected, onClick, index }: {
  title: string; description?: string; icon?: LucideIcon; selected: boolean; onClick: () => void; index?: string;
}) {
  return <motion.button type="button" whileTap={{ scale: .985 }} onClick={onClick} aria-pressed={selected}
    className={`focus-outline group flex min-h-[112px] w-full items-center gap-4 rounded-[22px] border p-5 text-left transition duration-300 sm:p-6 ${selected
      ? "border-[#4acaa9] bg-[#def8ee] text-[#113a3e] shadow-[0_18px_40px_rgba(31,148,122,0.14)]"
      : "border-[#dce6e3] bg-white text-[#193443] hover:-translate-y-0.5 hover:border-[#8bc9bb] hover:shadow-[0_16px_40px_rgba(7,45,50,0.08)]"}`}>
    {Icon && <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl ${selected ? "bg-[#b9efdc] text-[#137f70]" : "bg-[#f0f6f4] text-[#426978]"}`}><Icon size={23} strokeWidth={1.8} /></span>}
    <span className="min-w-0 flex-1"><span className="block text-lg font-semibold tracking-[-0.035em]">{title}</span>{description && <span className="mt-1 block text-sm leading-relaxed opacity-65">{description}</span>}</span>
    {selected ? <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#119c7d] text-white"><Check size={16} /></span> : <span className="text-xs font-semibold opacity-35">{index}</span>}
  </motion.button>;
}

export function MetricTile({ label, value, note, icon: Icon }: { label: string; value: string; note?: string; icon?: LucideIcon }) {
  return <div className="rounded-[20px] border border-[#dce9e6] bg-white p-5 shadow-[0_10px_25px_rgba(4,43,49,0.035)]">
    <div className="flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c9698]"><span>{label}</span>{Icon && <Icon size={17} className="text-[#3e9d91]" />}</div>
    <div className="mt-4 text-3xl font-semibold tracking-[-0.065em] text-[#11323f]">{value}</div>
    {note && <p className="mt-1 text-xs text-[#78918f]">{note}</p>}
  </div>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="flex min-h-48 flex-col items-center justify-center rounded-[24px] border border-dashed border-[#b8d1cc] bg-white/60 p-7 text-center text-[#1c4450]">
    <Compass className="text-[#65b6a6]" size={28} /><p className="mt-3 font-semibold">{title}</p><p className="mt-1 max-w-xs text-sm text-[#72918f]">{body}</p>
  </div>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`shimmer rounded-2xl ${className}`} />;
}
