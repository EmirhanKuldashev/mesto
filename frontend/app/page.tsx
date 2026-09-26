"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight, ArrowUpRight, Building2, Check, ChevronDown, Clock3, Compass,
  Layers3, MapPin, MoveUpRight, Navigation2, Route, ShieldCheck, Sparkles, Trees, Waypoints,
} from "lucide-react";
import { Brand, DemoBadge, DistrictInsightCard, Reveal, ScoreRing } from "@/components/concept-ui";

const steps = [
  { number: "01", title: "Расскажите о жизни", body: "Несколько быстрых касаний вместо длинной анкеты.", icon: Waypoints },
  { number: "02", title: "Покажите свой маршрут", body: "Отметьте важные точки и привычные способы передвижения.", icon: Navigation2 },
  { number: "03", title: "Увидьте целую картину", body: "Район, среда и сценарии выбора в одном пространстве.", icon: Compass },
];

const signals = [
  { title: "Среда рядом", body: "Школы, парки, сервисы и то, что происходит каждый день.", icon: Trees, color: "from-[#9ef0d0]/20" },
  { title: "Время в пути", body: "Работа и важные точки складываются в реальный маршрут.", icon: Route, color: "from-[#99bfff]/20" },
  { title: "Рынок жилья", body: "Стоимость в контексте удобства, а не отдельная цифра.", icon: Building2, color: "from-[#b8a9ff]/20" },
  { title: "Будущее района", body: "Запланированные изменения с честной пометкой о неопределённости.", icon: Layers3, color: "from-[#ffd6a8]/20" },
];

function HeroPreview() {
  return <motion.div initial={{ opacity: 0, y: 28, rotate: 1.5 }} animate={{ opacity: 1, y: 0, rotate: 0 }}
    transition={{ duration: .9, delay: .18, ease: [0.22, 1, 0.36, 1] }}
    className="relative mx-auto w-full max-w-[670px] lg:ml-auto">
    <div className="map-preview relative h-[530px] overflow-hidden rounded-[32px] border border-white/15 shadow-[0_45px_120px_rgba(1,13,25,0.55)] sm:h-[610px]">
      <div className="absolute left-6 top-6 z-10 flex items-center gap-2 rounded-full border border-white/15 bg-[#0a2735]/75 px-4 py-2 text-xs font-semibold text-[#d9f0ee] backdrop-blur-md"><span className="h-2 w-2 rounded-full bg-[#96efd2] shadow-[0_0_14px_#95e6ce]" />Красноярск · карта жизни</div>
      <svg className="absolute inset-0 h-full w-full opacity-65" viewBox="0 0 640 610" fill="none" aria-hidden="true">
        <path d="M-60 402C102 438 118 327 276 337C414 346 430 252 711 260" stroke="#88b8c2" strokeWidth="18" opacity=".14" />
        <path d="M-50 405C102 438 118 327 276 337C414 346 430 252 711 260" stroke="#c8f2e7" strokeWidth="2" opacity=".55" />
        <path d="M94-25C153 123 160 216 321 273C439 314 502 505 541 639" stroke="#93c1c9" strokeWidth="13" opacity=".14" />
        <path d="M94-25C153 123 160 216 321 273C439 314 502 505 541 639" stroke="#ddf6e8" strokeWidth="2" opacity=".4" />
        <path d="M30 149C166 224 240 100 376 131C491 156 521 73 682 80" stroke="#a4d1ce" strokeWidth="3" strokeDasharray="8 12" opacity=".45" />
        <path d="M101 538C230 480 353 497 425 416C488 344 530 370 654 342" stroke="#a4d1ce" strokeWidth="3" strokeDasharray="8 12" opacity=".45" />
        <path d="M173 421C228 375 290 371 347 299C392 242 455 194 502 169" stroke="#9ff3d9" strokeWidth="3" strokeDasharray="7 9" />
        <circle cx="173" cy="421" r="5" fill="#a9f5df" /><circle cx="347" cy="299" r="5" fill="#a9f5df" /><circle cx="502" cy="169" r="5" fill="#a9f5df" />
      </svg>
      <div className="absolute left-[20%] top-[65%] z-10 flex items-center gap-2 rounded-full border border-[#9deed6]/30 bg-[#092935]/80 px-3 py-2 text-xs text-white shadow-xl backdrop-blur-md"><span className="glow-dot h-2 w-2 rounded-full bg-[#a6f5dc]" />Работа</div>
      <div className="absolute right-[14%] top-[25%] z-10 flex items-center gap-2 rounded-full border border-[#9deed6]/30 bg-[#092935]/80 px-3 py-2 text-xs text-white shadow-xl backdrop-blur-md"><span className="glow-dot h-2 w-2 rounded-full bg-[#a6f5dc]" />Дом</div>
      <div className="absolute left-[47%] top-[49%] z-10 grid h-14 w-14 place-items-center rounded-2xl border border-white/30 bg-[#95eed6]/20 text-[#c6ffe9] shadow-[0_0_45px_rgba(137,235,207,.45)] backdrop-blur-md"><MapPin size={26} /></div>
      <div className="absolute inset-x-5 bottom-5 z-20 rounded-[25px] border border-white/20 bg-[#082130]/90 p-5 shadow-[0_20px_60px_rgba(0,0,0,0.3)] backdrop-blur-xl sm:inset-x-auto sm:bottom-8 sm:left-8 sm:w-[360px] sm:p-6">
        <div className="flex items-start justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#8edacb]">Пример результата</p><h3 className="mt-2 text-2xl font-semibold tracking-[-0.055em]">Советский район</h3><p className="mt-1 text-xs text-[#a8c8cc]">Место для вашего сценария</p></div><span className="rounded-full bg-[#9ff1d8]/15 px-3 py-1 text-sm font-bold text-[#b1f8e2]">86 / 100</span></div>
        <div className="mt-5 h-px bg-white/10" />
        <div className="mt-4 flex items-center justify-between text-xs text-[#b8d1d0]"><span className="flex items-center gap-1.5"><Clock3 size={14} className="text-[#9fe9d5]" />22 мин до работы</span><span className="flex items-center gap-1.5"><Trees size={14} className="text-[#9fe9d5]" />Зелень рядом</span></div>
      </div>
      <div className="absolute bottom-[205px] right-5 z-20 hidden rounded-2xl border border-white/15 bg-[#0b2939]/80 px-4 py-3 text-xs text-[#d5edeb] backdrop-blur-lg sm:block"><span className="block text-[10px] uppercase tracking-[.18em] text-[#9ce7d2]">Путь до работы</span><strong className="mt-1 block text-xl font-semibold">22 мин <span className="text-sm font-normal text-[#91b9bc]">/ день</span></strong></div>
    </div>
    <div className="absolute -bottom-7 -left-5 z-30 hidden rounded-2xl border border-white/15 bg-[#123240] px-5 py-4 shadow-2xl lg:block"><span className="text-[11px] font-bold uppercase tracking-[.18em] text-[#91daca]">Не только адрес</span><p className="mt-1 text-sm font-medium">Вся жизнь вокруг него.</p></div>
  </motion.div>;
}

export default function Home() {
  return <main className="page-shell">
    <section className="mesh-background relative min-h-screen overflow-hidden">
      <div className="content-shell relative z-10">
        <header className="flex items-center justify-between py-6 sm:py-8">
          <Brand />
          <nav className="hidden items-center gap-8 text-sm font-medium text-[#bbd3d2] md:flex" aria-label="Навигация">
            <a href="#how" className="hover:text-white">Как работает</a><a href="#signals" className="hover:text-white">Что анализируем</a><a href="#value" className="hover:text-white">Результат</a>
          </nav>
          <Link href="/onboarding" className="focus-outline rounded-full border border-[#a2f5db]/35 px-5 py-2.5 text-xs font-bold text-[#b7fbe5] transition hover:bg-[#a2f5db]/10">Начать <ArrowUpRight className="ml-1 inline" size={15} /></Link>
        </header>

        <div className="grid min-h-[calc(100vh-110px)] items-center gap-16 pb-24 pt-12 lg:grid-cols-[1.05fr_.95fr] lg:gap-7 lg:pt-0">
          <div className="relative z-10 max-w-[760px]">
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .6 }} className="mb-7 flex flex-wrap items-center gap-3"><span className="demo-chip"><Sparkles size={13} />Новый взгляд на выбор жилья</span><span className="text-xs text-[#7fa3ad]">Красноярск · концепт MVP</span></motion.div>
            <motion.h1 initial={{ opacity: 0, y: 25 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .75, delay: .08 }} className="display-title max-w-[740px]">Найди место, которое подойдёт <span className="gradient-text">не квартире, а жизни.</span></motion.h1>
            <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7, delay: .18 }} className="mt-8 max-w-[580px] text-base leading-[1.8] text-[#aec7ca] sm:text-lg">МЕСТО анализирует районы, инфраструктуру, дорогу, развитие территории и ваши жизненные сценарии — чтобы показать, где действительно удобно жить.</motion.p>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7, delay: .28 }} className="mt-10 flex flex-wrap items-center gap-3">
              <Link href="/onboarding" className="primary-button">Начать подбор <ArrowRight size={18} /></Link>
              <Link href="/analysis?demo=1" className="secondary-button">Посмотреть демо <MoveUpRight size={17} /></Link>
            </motion.div>
            <div className="mt-12 flex flex-wrap items-center gap-x-7 gap-y-3 text-xs text-[#8daeb0]"><span className="flex items-center gap-2"><Check size={14} className="text-[#91efd1]" />Меньше полей — больше смысла</span><span className="flex items-center gap-2"><Check size={14} className="text-[#91efd1]" />Сценарий за несколько минут</span></div>
          </div>
          <HeroPreview />
        </div>
        <a href="#how" className="absolute bottom-7 left-1/2 hidden -translate-x-1/2 items-center gap-2 text-[11px] font-bold uppercase tracking-[.2em] text-[#7fa2a9] hover:text-white lg:flex">Листайте дальше <ChevronDown size={15} /></a>
      </div>
    </section>

    <section id="how" className="relative border-t border-white/5 bg-[#0b1e2b] py-24 sm:py-32">
      <div className="content-shell">
        <Reveal className="max-w-[790px]"><p className="eyebrow">Просто начать</p><h2 className="section-title mt-5">Не анкета. <span className="gradient-text">Диалог о вашей жизни.</span></h2><p className="mt-6 max-w-[600px] text-lg leading-relaxed text-[#9cb7bc]">Вы отвечаете быстрыми касаниями. МЕСТО собирает привычки, маршруты и приоритеты в понятную картину.</p></Reveal>
        <div className="mt-14 grid gap-4 md:grid-cols-3">{steps.map((step, index) => <Reveal key={step.number} delay={index * .1} className="glass-panel relative min-h-[290px] overflow-hidden rounded-[26px] p-7 sm:p-8">
          <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-[#9ff1d8]/10 text-[#a9f7dc]"><step.icon size={24} /></span><span className="text-5xl font-light tracking-[-0.1em] text-white/10">{step.number}</span></div>
          <h3 className="mt-12 text-2xl font-semibold tracking-[-0.05em]">{step.title}</h3><p className="mt-3 max-w-xs text-sm leading-relaxed text-[#9cb5b9]">{step.body}</p>
        </Reveal>)}</div>
      </div>
    </section>

    <section id="signals" className="relative bg-[#f3f8f6] py-24 text-[#11303e] sm:py-32">
      <div className="content-shell">
        <Reveal className="flex flex-col justify-between gap-7 lg:flex-row lg:items-end"><div className="max-w-[720px]"><p className="text-[11px] font-bold uppercase tracking-[.23em] text-[#168b77]">Что анализируем</p><h2 className="section-title mt-5">Место — это <span className="text-[#198e7b]">больше, чем точка на карте.</span></h2></div><p className="max-w-sm text-base leading-relaxed text-[#61808a]">Смотрим на район так, как вы ощущаете его каждый день: через дорогу, среду, возможности и планы.</p></Reveal>
        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{signals.map((signal, index) => <Reveal key={signal.title} delay={index * .08} className={`fine-grid relative min-h-[270px] overflow-hidden rounded-[24px] border border-[#dfeae7] bg-gradient-to-br ${signal.color} via-white to-white p-7 shadow-[0_20px_60px_rgba(16,53,60,.06)]`}>
          <signal.icon size={27} className="text-[#167e77]" strokeWidth={1.7} /><h3 className="mt-14 text-xl font-semibold tracking-[-0.045em]">{signal.title}</h3><p className="mt-3 text-sm leading-relaxed text-[#69848b]">{signal.body}</p>
        </Reveal>)}</div>
      </div>
    </section>

    <section id="value" className="relative overflow-hidden bg-[#0c2634] py-24 sm:py-32">
      <div className="content-shell grid items-center gap-14 lg:grid-cols-[.9fr_1.1fr]">
        <Reveal><p className="eyebrow">Что вы получаете</p><h2 className="section-title mt-5">Не просто оценку. <span className="gradient-text">Причины, маршрут и выбор.</span></h2><p className="mt-6 max-w-lg text-base leading-[1.8] text-[#a5c0c1]">В концепте результата видно, почему район подходит, где есть компромиссы и как меняется ответ для разных жизненных сценариев.</p>
          <div className="mt-8 space-y-4 text-sm text-[#d3e7e6]"><p className="flex items-start gap-3"><ShieldCheck size={19} className="shrink-0 text-[#9ef1d8]" />Понятные аргументы рядом с каждой оценкой.</p><p className="flex items-start gap-3"><Layers3 size={19} className="shrink-0 text-[#9ef1d8]" />Разделение текущей среды и планируемых изменений.</p><p className="flex items-start gap-3"><Compass size={19} className="shrink-0 text-[#9ef1d8]" />Карта, которая ведёт к деталям района.</p></div>
          <Link href="/analysis?demo=1" className="primary-button mt-10">Открыть демо-результат <ArrowRight size={17} /></Link>
        </Reveal>
        <Reveal delay={.15} className="relative"><div className="absolute -inset-12 rounded-full bg-[#63d6be]/[.075] blur-3xl" /><div className="relative rounded-[34px] border border-white/10 bg-[#153442] p-5 shadow-[0_40px_110px_rgba(0,0,0,.25)] sm:p-8">
          <div className="mb-5 flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-[.2em] text-[#9fd6cb]">Preview · МЕСТО</span><DemoBadge /></div>
          <div className="flex flex-col items-center gap-6 rounded-[27px] border border-white/10 bg-[#0e2937] p-7 sm:flex-row"><ScoreRing value={86} /><div><p className="eyebrow">Ваше место</p><h3 className="mt-3 text-3xl font-semibold tracking-[-.06em]">Советский район</h3><p className="mt-3 text-sm leading-relaxed text-[#a8c4c6]">Баланс маршрутов, инфраструктуры и среды для демонстрационного сценария.</p><div className="mt-6 flex gap-2"><span className="soft-chip">22 мин до работы</span><span className="soft-chip">Парки рядом</span></div></div></div>
          <div className="mt-5"><DistrictInsightCard compact /></div>
        </div></Reveal>
      </div>
    </section>

    <section className="bg-[#071521] py-20">
      <div className="content-shell"><Reveal className="flex flex-col gap-8 rounded-[30px] border border-[#9af1d9]/20 bg-gradient-to-r from-[#143f48] to-[#102b3a] p-8 sm:p-12 lg:flex-row lg:items-center lg:justify-between">
        <div><p className="eyebrow">Почему это полезно</p><h2 className="mt-4 max-w-2xl text-3xl font-semibold tracking-[-.06em] sm:text-5xl">Выбирайте жизнь, которая складывается каждый день.</h2><p className="mt-4 text-sm text-[#a8c8c8]">Попробуйте сценарий в своём темпе. Пример результата доступен без регистрации.</p></div>
        <Link href="/onboarding" className="primary-button shrink-0">Начать подбор <ArrowRight size={18} /></Link>
      </Reveal>
      <footer className="mt-14 flex flex-col justify-between gap-5 border-t border-white/10 pt-8 text-xs text-[#789ba2] sm:flex-row sm:items-center"><Brand /><p>МЕСТО · концепт интерфейса. Показатели на демо-экранах иллюстративны.</p></footer></div>
    </section>
  </main>;
}
