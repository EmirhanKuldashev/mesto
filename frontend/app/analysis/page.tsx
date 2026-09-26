"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Check, Compass, MapPin, Route, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Brand, DemoBadge } from "@/components/concept-ui";

const phases = [
  { icon: MapPin, title: "Собираем инфраструктуру", detail: "Школы, парки и повседневные места" },
  { icon: Route, title: "Проверяем транспорт", detail: "Маршруты и доступность" },
  { icon: Compass, title: "Оцениваем среду", detail: "Что важно для жизни сегодня" },
  { icon: MapPin, title: "Смотрим на развитие", detail: "Планы и изменения района" },
  { icon: Sparkles, title: "Собираем ваш индекс", detail: "Как будет выглядеть результат" },
];
export default function AnalysisPage() {
  const router = useRouter();
  const reduced = useReducedMotion();
  const [phase, setPhase] = useState(0);
  const [message, setMessage] = useState("");
  useEffect(() => {
    setMessage(sessionStorage.getItem("mesto-save-status") ?? "");
    sessionStorage.removeItem("mesto-save-status");
    const timers = phases.slice(1).map((_, index) => window.setTimeout(() => setPhase(index + 1), reduced ? (index + 1) * 120 : (index + 1) * 800));
    timers.push(window.setTimeout(() => router.replace("/results?demo=1"), reduced ? 750 : 5000));
    return () => timers.forEach(window.clearTimeout);
  }, [router, reduced]);
  return <main className="page-shell mesh-background relative min-h-screen"><header className="content-shell relative z-10 flex h-20 items-center justify-between"><Brand /><DemoBadge /></header>
    <div className="content-shell relative z-10 flex min-h-[calc(100vh-80px)] flex-col items-center justify-center pb-20 text-center"><motion.div initial={{ scale: .84, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="relative mb-10 grid h-28 w-28 place-items-center rounded-[35px] border border-[#9eeed6]/25 bg-[#9eeed6]/10 text-[#a9f4dd]"><Sparkles size={42} /><motion.span className="absolute inset-[-14px] rounded-[45px] border border-[#a4f2dd]/20" animate={reduced ? {} : { scale: [1, 1.18, 1], opacity: [.65, .2, .65] }} transition={{ repeat: Infinity, duration: 2.2 }} /></motion.div>
      <p className="eyebrow">Ваше место становится ближе</p><h1 className="mt-5 max-w-3xl text-[clamp(2.7rem,6vw,5.8rem)] font-semibold leading-[1.03] tracking-[-.07em]">{phase === phases.length - 1 ? <>Ваше место <span className="gradient-text">найдено</span></> : <>Собираем картину <span className="gradient-text">вашей жизни</span></>}</h1>
      <p className="mt-5 max-w-xl text-sm leading-relaxed text-[#a5bdc0]">Это демонстрация будущего анализа. На следующем экране показан пример результата, а не расчёт по вашим ответам.</p>
      {message && <p role="status" className="mt-5 max-w-xl rounded-2xl border border-[#e5b8a0]/25 bg-[#ba7750]/10 p-3 text-sm text-[#f3c7ac]">{message}</p>}
      <div className="mt-12 w-full max-w-xl space-y-3 text-left">{phases.map((item, index) => <motion.div key={item.title} initial={{ opacity: .4, x: 10 }} animate={{ opacity: index <= phase ? 1 : .38, x: 0 }} className={`flex items-center gap-4 rounded-[20px] border p-4 ${index <= phase ? "border-[#9cebd7]/30 bg-white/10" : "border-white/10 bg-white/[.035]"}`}><span className="grid h-11 w-11 place-items-center rounded-xl bg-[#a9f5df]/10 text-[#a9f5df]"><item.icon size={20} /></span><span className="flex-1"><strong className="block text-sm">{item.title}</strong><small className="text-[#9cb9b9]">{item.detail}</small></span>{index < phase && <Check className="text-[#9ee8d3]" size={19} />}</motion.div>)}</div>
      <Link href="/results?demo=1" className="mt-9 inline-flex items-center gap-2 text-sm font-semibold text-[#a8f0da]">Посмотреть пример сразу <ArrowRight size={16} /></Link>
    </div></main>;
}
