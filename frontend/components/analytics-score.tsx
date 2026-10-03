"use client";

import { motion } from "framer-motion";
import { AlertTriangle, ArrowUpRight, Check, Sparkles } from "lucide-react";
import type { CategoryScores, DistrictScoreResponse } from "@/types/analytics";
import { SignalPanel } from "@/components/signal-panel";
import { DistrictAiSummary } from "@/components/district-ai-summary";

const categories: { key: keyof CategoryScores; title: string; description: string }[] = [
  { key: "infrastructure", title: "Инфраструктура", description: "Школы, медицина, парки и повседневные места" },
  { key: "transport", title: "Доступность остановок", description: "Плотность остановок, без расчёта маршрутов и времени в пути" },
];

function number(value: number | null) { return value === null ? "—" : Math.round(value).toString(); }

export function AnalyticsScore({ score }: { score: DistrictScoreResponse }) {
  return <div className="space-y-6">
    <DistrictAiSummary districtId={score.district.id} />
    <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
      <motion.article initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .5 }}
        className="rounded-[30px] border border-white/15 bg-gradient-to-br from-[#185652] via-[#103c47] to-[#0b2939] p-7 text-white shadow-[0_25px_80px_rgba(4,24,35,.25)] sm:p-9">
        <p className="text-xs font-bold uppercase tracking-[.22em] text-[#a4e9d3]">MESTO SCORE · {score.district.name}</p>
        <div className="mt-7 flex items-end gap-2"><span className="text-[clamp(4.5rem,11vw,8rem)] font-semibold leading-none tracking-[-.09em]">{number(score.score)}</span><span className="pb-2 text-2xl text-[#a7ceca]">/100</span></div>
        <p className="mt-5 text-sm text-[#b9d4d0]">Базовый индекс текущей инфраструктуры и доступности остановок.</p>
        <p className="mt-3 text-sm text-[#b9d4d0]">Покрытие компонентов MESTO: {Math.round(score.confidence * 100)}%</p>
        <p className="mt-2 text-xs leading-relaxed text-[#b9d4d0]">100% покрытия означает, что рассчитаны оба обязательных компонента. Это не полнота информации о районе. Балл 100 означает достижение текущих порогов методики.</p>
      </motion.article>
      <div className="grid grid-cols-2 gap-4">
        {[{ label: "Growth · развитие", value: score.future_growth_score }, { label: "Будущий сценарий", value: score.future_score }].map((item, index) =>
          <motion.div key={item.label} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .12 + index * .1 }}
            className="flex flex-col justify-between rounded-[26px] border border-[#dbe9e4] bg-white p-6 text-[#153c44]">
            <span className="text-xs font-bold uppercase tracking-[.15em] text-[#73918e]">{item.label}</span>
            <div className="mt-7 text-4xl font-semibold tracking-[-.07em] sm:text-5xl">{number(item.value)}<span className="ml-1 text-base text-[#7c9693]">/100</span></div>
          </motion.div>)}
      </div>
    </div>

    <section className="rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
      <h2 className="text-2xl font-semibold tracking-[-.04em]">Компоненты MESTO Score</h2>
      <div className="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{categories.map(({ key, title, description }, index) => {
        const value = score.categories[key];
        return <motion.div key={key} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .15 + index * .07 }}
          className="rounded-[20px] bg-[#f1f8f5] p-5">
          <div className="flex items-start justify-between gap-3"><h3 className="font-semibold">{title}</h3><span className="text-xl font-bold text-[#168e79]">{number(value)}</span></div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#dcebe6]"><motion.div initial={{ width: 0 }} animate={{ width: `${value ?? 0}%` }} transition={{ duration: .7, delay: .2 + index * .07 }} className="h-full rounded-full bg-[#2fb593]" /></div>
          <p className="mt-3 text-xs leading-relaxed text-[#647f80]">{value === null ? "Недостаточно данных" : description}</p>
        </motion.div>;
      })}</div>
    </section>

    <section className="grid gap-5 lg:grid-cols-2">
      <div className="rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
        <h2 className="text-xl font-semibold">Что учтено в MESTO</h2>
        {score.reasons.length ? <ul className="mt-5 space-y-3">{score.reasons.map((reason, index) => <li key={`${reason}-${index}`} className="flex gap-3 text-sm leading-relaxed"><Check size={18} className="mt-0.5 shrink-0 text-[#1aa17f]" />{reason}</li>)}</ul> : <p className="mt-4 text-sm text-[#6b8584]">Подтверждённых причин пока нет.</p>}
      </div>
      <div className="rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
        <h2 className="text-xl font-semibold">Ограничения данных</h2>
        {score.warnings.length ? <ul className="mt-5 space-y-3">{score.warnings.map((warning, index) => <li key={`${warning}-${index}`} className="flex gap-3 text-sm leading-relaxed"><AlertTriangle size={17} className="mt-0.5 shrink-0 text-[#d9963b]" />{warning}</li>)}</ul> : <p className="mt-4 text-sm text-[#6b8584]">Дополнительных предупреждений нет.</p>}
      </div>
    </section>

    <section className="rounded-[28px] border border-white/10 bg-[#0b2c3a] p-6 text-white sm:p-8">
      <div className="flex items-center gap-2 text-[#a8ead6]"><Sparkles size={19} /><h2 className="text-xl font-semibold text-white">Growth и будущий сценарий</h2></div>
      <p className="mt-3 text-sm text-[#abc7c6]">Планируемые изменения показаны отдельно и не входят в MESTO Score. Реализация не гарантирована.</p>
      <div className="mt-6 flex flex-wrap items-center gap-4 text-sm"><span>Сегодня <strong className="ml-2 text-2xl">{number(score.current_score)}</strong></span><ArrowUpRight size={18} className="text-[#8fd9c3]" /><span>Будущий сценарий <strong className="ml-2 text-2xl">{number(score.future_score)}</strong></span></div>
      {score.future_factors.length ? <div className="mt-6 grid gap-3 sm:grid-cols-2">{score.future_factors.map((factor, index) =>
        <motion.div key={`${factor.object_id}-${index}`} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: .15 + index * .08 }}
          className="rounded-[20px] border border-white/10 bg-white/[.07] p-5"><div className="flex justify-between gap-3"><h3 className="font-semibold">{factor.name}</h3><span className="text-[#a5ead4]">{factor.year ?? "Срок неизвестен"}</span></div><p className="mt-2 text-sm text-[#adc9c8]">{factor.reason}</p></motion.div>)}</div>
        : <p className="mt-5 text-sm text-[#abc7c6]">{score.external_signal_impacts.length ? "Потенциал основан на внешних сигналах ниже; будущих объектов пока нет." : "Подтверждённых будущих факторов пока нет."}</p>}
    </section>
    <SignalPanel districtId={score.district.id} />
  </div>;
}
