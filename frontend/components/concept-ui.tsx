"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight, Check, Compass, MapPin, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { demoDistrict, demoScenarios } from "@/lib/demo-data";

export function Brand({ compact = false }: { compact?: boolean }) {
  return <Link href="/" className="focus-outline inline-flex items-center gap-3 font-semibold tracking-[-0.06em] text-white" aria-label="МЕСТО — главная">
    <span className="grid h-10 w-10 place-items-center rounded-[15px] border border-[#9ef5d9]/30 bg-[#9ef5d9]/15 text-[#a8f7df]"><MapPin size={20} strokeWidth={2.4} /></span>
    {!compact && <span className="text-[25px]">МЕСТО<span className="ml-1 text-[#9ef5d9]">.</span></span>}
  </Link>;
}

export function DemoBadge({ light = false }: { light?: boolean }) {
  return <span className={light ? "inline-flex items-center gap-1.5 rounded-full border border-[#bad9d3] bg-white px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.13em] text-[#376979]" : "demo-chip"}>
    <Sparkles size={12} /> Демо-данные
  </span>;
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

export function ScoreRing({ value, size = "large", dark = false }: { value: number; size?: "large" | "small"; dark?: boolean }) {
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const small = size === "small";
  return <div className={`relative shrink-0 ${small ? "h-32 w-32" : "h-48 w-48 sm:h-56 sm:w-56"}`}>
    <svg className="h-full w-full -rotate-90" viewBox="0 0 140 140" aria-hidden="true">
      <circle cx="70" cy="70" r={radius} fill="none" stroke={dark ? "rgba(24,77,84,.14)" : "rgba(255,255,255,.12)"} strokeWidth="8" />
      <motion.circle cx="70" cy="70" r={radius} fill="none" stroke={dark ? "#0d9c80" : "#9cf2d6"} strokeWidth="8" strokeLinecap="round"
        strokeDasharray={circumference} initial={{ strokeDashoffset: circumference }}
        whileInView={{ strokeDashoffset: circumference * (1 - value / 100) }} viewport={{ once: true }}
        transition={{ duration: 1.6, ease: [0.22, 1, 0.36, 1], delay: .2 }} />
    </svg>
    <div className={`absolute inset-0 flex flex-col items-center justify-center ${dark ? "text-[#123541]" : "text-white"}`}>
      <span className={`${small ? "text-4xl" : "text-6xl"} font-semibold tracking-[-0.09em]`}>{value}</span>
      <span className={`text-[10px] font-bold uppercase tracking-[0.2em] ${dark ? "text-[#6b9090]" : "text-[#a6d9d3]"}`}>из 100</span>
    </div>
  </div>;
}

export function MetricTile({ label, value, note, icon: Icon }: { label: string; value: string; note?: string; icon?: LucideIcon }) {
  return <div className="rounded-[20px] border border-[#dce9e6] bg-white p-5 shadow-[0_10px_25px_rgba(4,43,49,0.035)]">
    <div className="flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c9698]"><span>{label}</span>{Icon && <Icon size={17} className="text-[#3e9d91]" />}</div>
    <div className="mt-4 text-3xl font-semibold tracking-[-0.065em] text-[#11323f]">{value}</div>
    {note && <p className="mt-1 text-xs text-[#78918f]">{note}</p>}
  </div>;
}

export function DistrictInsightCard({ compact = false }: { compact?: boolean }) {
  return <article className="rounded-[26px] border border-[#dce9e5] bg-white p-6 text-[#173644] shadow-[0_24px_60px_rgba(4,39,49,0.08)] sm:p-7">
    <div className="flex items-start justify-between gap-4">
      <div><span className="text-[11px] font-bold uppercase tracking-[0.19em] text-[#358f80]">Инсайт района</span><h3 className="mt-2 text-2xl font-semibold tracking-[-0.055em]">{demoDistrict.name}</h3></div>
      <span className="rounded-full bg-[#dff7ee] px-3 py-1.5 text-sm font-bold text-[#137d6d]">{demoDistrict.score} / 100</span>
    </div>
    <p className="mt-4 text-sm leading-relaxed text-[#658080]">Пример того, как район может подходить вашему сценарию.</p><div className="mt-4 space-y-2 text-xs leading-relaxed text-[#557a78]"><p>+ Инфраструктура, парки и транспорт рядом</p><p>+ Планируемые общественные пространства</p><p className="text-[#9c7864]">− Часть объектов только планируется; цены выше среднего</p></div>
    {!compact && <div className="mt-6 space-y-3">{demoDistrict.categories.map((item) =>
      <div key={item.label} className="grid grid-cols-[105px_1fr_28px] items-center gap-3 text-xs">
        <span className="text-[#638080]">{item.label}</span><div className="h-1.5 overflow-hidden rounded-full bg-[#e8f0ed]"><motion.div initial={{ width: 0 }} whileInView={{ width: `${item.value}%` }} viewport={{ once: true }} transition={{ duration: .8 }} className="h-full rounded-full bg-[#34b69d]" /></div>
        <span className="text-right font-semibold text-[#26535c]">{item.value}</span>
      </div>)}</div>}
    <Link href="/district" className="focus-outline mt-6 inline-flex items-center gap-2 text-sm font-bold text-[#138d79] hover:text-[#0d685d]">Открыть карту района <ArrowUpRight size={16} /></Link>
  </article>;
}

export function ScenarioCard({ scenario }: { scenario: (typeof demoScenarios)[number] }) {
  return <motion.article whileHover={{ y: -5 }} className="group rounded-[26px] border border-white/10 bg-white/[0.065] p-6 transition-colors hover:border-[#a3f4db]/35 hover:bg-white/[0.085] sm:p-7">
    <div className="flex items-start justify-between gap-4">
      <div><span className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#8bd9cc]">Сценарий</span><h3 className="mt-3 text-2xl font-semibold tracking-[-0.05em]">{scenario.title}</h3></div>
      <span className="rounded-full border border-[#9af4d8]/25 bg-[#9af4d8]/10 px-3 py-1.5 text-sm font-bold text-[#a2f2d9]">{scenario.score}/100</span>
    </div>
    <p className="mt-2 text-sm text-[#a8c0c3]">{scenario.subtitle}</p>
    <ul className="mt-7 space-y-3">{scenario.details.map((detail) => <li key={detail} className="flex items-start gap-2 text-sm text-[#d8e8e7]"><Check size={16} className="mt-0.5 shrink-0 text-[#91ebd1]" />{detail}</li>)}</ul>
  </motion.article>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="flex min-h-48 flex-col items-center justify-center rounded-[24px] border border-dashed border-[#b8d1cc] bg-white/60 p-7 text-center text-[#1c4450]">
    <Compass className="text-[#65b6a6]" size={28} /><p className="mt-3 font-semibold">{title}</p><p className="mt-1 max-w-xs text-sm text-[#72918f]">{body}</p>
  </div>;
}


export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`shimmer rounded-2xl ${className}`} />;
}
