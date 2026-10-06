"use client";

import { motion } from "framer-motion";
import { ArrowUpRight, Sparkles } from "lucide-react";
import type { DistrictScoreResponse } from "@/types/analytics";
import { SignalPanel } from "@/components/signal-panel";
import { ObjectiveScore } from "@/components/objective-score";
import { displayScore, objectiveValue } from "@/lib/objective-presentation";
import { DistrictAiSummary } from "@/components/district-ai-summary";

function number(value: number | null) { return value === null ? "—" : Math.round(value).toString(); }

export function AnalyticsScore({ score }: { score: DistrictScoreResponse }) {
  return <div className="space-y-6">
    <ObjectiveScore score={score} />
    <DistrictAiSummary districtId={score.district.id} />
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        {[{ label: "Growth · развитие", value: score.future_growth_score }, { label: "Будущий сценарий", value: score.future_score }].map((item, index) =>
          <motion.div key={item.label} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .12 + index * .1 }}
            className="flex flex-col justify-between rounded-[26px] border border-[#dbe9e4] bg-white p-6 text-[#153c44]">
            <span className="text-xs font-bold uppercase tracking-[.15em] text-[#73918e]">{item.label}</span>
            <div className="mt-7 text-4xl font-semibold tracking-[-.07em] sm:text-5xl">{number(item.value)}<span className="ml-1 text-base text-[#7c9693]">/100</span></div>
          </motion.div>)}
      </div>
    </div>

    <section className="rounded-[28px] border border-white/10 bg-[#0b2c3a] p-6 text-white sm:p-8">
      <div className="flex items-center gap-2 text-[#a8ead6]"><Sparkles size={19} /><h2 className="text-xl font-semibold text-white">Growth и будущий сценарий</h2></div>
      <p className="mt-3 text-sm text-[#abc7c6]">Планируемые изменения показаны отдельно и не входят в MESTO Score. Реализация не гарантирована.</p>
      {score.warnings.some((warning) => warning.startsWith("Growth:") || warning.includes("синтетические")) &&
        <ul className="mt-4 space-y-2 text-sm text-[#abc7c6]">{score.warnings
          .filter((warning) => warning.startsWith("Growth:") || warning.includes("синтетические"))
          .map((warning) => <li key={warning}>{warning}</li>)}</ul>}
      <div className="mt-6 flex flex-wrap items-center gap-4 text-sm"><span>Сегодня <strong className="ml-2 text-2xl">{displayScore(objectiveValue(score))}</strong></span><ArrowUpRight size={18} className="text-[#8fd9c3]" /><span>Будущий сценарий <strong className="ml-2 text-2xl">{number(score.future_score)}</strong></span></div>
      {score.future_factors.length ? <div className="mt-6 grid gap-3 sm:grid-cols-2">{score.future_factors.map((factor, index) =>
        <motion.div key={`${factor.object_id}-${index}`} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: .15 + index * .08 }}
          className="rounded-[20px] border border-white/10 bg-white/[.07] p-5"><div className="flex justify-between gap-3"><h3 className="font-semibold">{factor.name}</h3><span className="text-[#a5ead4]">{factor.year ?? "Срок неизвестен"}</span></div><p className="mt-2 text-sm text-[#adc9c8]">{factor.reason}</p></motion.div>)}</div>
        : <p className="mt-5 text-sm text-[#abc7c6]">{score.external_signal_impacts.length ? "Потенциал основан на внешних сигналах ниже; будущих объектов пока нет." : "Подтверждённых будущих факторов пока нет."}</p>}
    </section>
    <SignalPanel districtId={score.district.id} />
  </div>;
}
