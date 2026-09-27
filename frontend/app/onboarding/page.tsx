"use client";

import dynamic from "next/dynamic";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Baby, Bike, BriefcaseBusiness, Bus, CarFront, Check, Clock3, Heart, Home, Leaf, MapPin, RotateCcw, ShieldCheck, Sparkles, Trees, Users, UserRound, Wallet, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Brand, SelectionCard } from "@/components/concept-ui";
import { useAnalytics } from "@/lib/analytics-store";
import { type Coordinates, type LifePoint, type OnboardingDraft, type PreferenceName, useOnboarding } from "@/lib/onboarding-store";

const LifePointMap = dynamic(() => import("@/components/life-point-map"), { ssr: false });
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const steps = [
  { title: "Кто будет жить в новом месте?", caption: "Начнём с вашего жизненного сценария." },
  { title: "Что вы планируете?", caption: "Покупку и аренду можно сравнить." },
  { title: "Какой бюджет комфортен?", caption: "Выберите диапазон одним касанием." },
  { title: "Сколько времени готовы тратить на дорогу?", caption: "Ориентир на одну поездку в обычный день." },
  { title: "Как вы передвигаетесь?", caption: "Можно выбрать несколько вариантов." },
  { title: "Что для вас важно рядом?", caption: "Выберите до четырёх приоритетов." },
  { title: "Какой ритм места вам ближе?", caption: "Коснитесь точки на каждой шкале. Можно пропустить." },
  { title: "Что может измениться?", caption: "Учтём планы на ближайшие годы." },
  { title: "Где ваши важные места?", caption: "Коснитесь карты, чтобы отметить точку. Этот шаг можно пропустить." },
  { title: "Ваш сценарий готов", caption: "Посмотрите, какие ответы вы выбрали." },
];
const household = [
  { id: "single", title: "Для себя", description: "Свой ритм и свои маршруты", icon: UserRound },
  { id: "couple", title: "Для пары", description: "Учитываем жизнь вдвоём", icon: Heart },
  { id: "family", title: "Для семьи", description: "Место для повседневной жизни", icon: Users },
  { id: "family_with_relatives", title: "Большая семья", description: "Больше людей, больше маршрутов", icon: Home },
] as const;
const goals = [
  { id: "buy", title: "Покупка", description: "Ищу дом надолго", icon: Home },
  { id: "rent", title: "Аренда", description: "Хочу гибкости", icon: Wallet },
  { id: "compare", title: "Сравнить оба", description: "Пока выбираю сценарий", icon: Sparkles },
] as const;
const transports = [
  { id: "car", title: "На машине", description: "Личный транспорт", icon: CarFront },
  { id: "public_transport", title: "Общественный", description: "Автобус и другие маршруты", icon: Bus },
  { id: "walking", title: "Пешком", description: "Всё нужное рядом", icon: MapPin },
  { id: "bicycle", title: "На велосипеде", description: "Активное передвижение", icon: Bike },
] as const;
const priorities = [
  { id: "price_vs_time", title: "Ближе к работе", icon: BriefcaseBusiness, value: 100 },
  { id: "education_weight", title: "Школы и детсады", icon: Baby, value: 90 },
  { id: "parks_weight", title: "Больше зелени", icon: Trees, value: 90 },
  { id: "quiet_active", title: "Тихий район", icon: Home, value: 0 },
  { id: "future_growth_weight", title: "Развитие района", icon: Sparkles, value: 90 },
  { id: "housing_price_weight", title: "Цена", icon: Wallet, value: 90 },
  { id: "safety_weight", title: "Безопасность", icon: ShieldCheck, value: 90 },
  { id: "transport_weight", title: "Транспорт", icon: Bus, value: 90 },
  { id: "shopping_weight", title: "Магазины рядом", icon: Home, value: 90 },
] as const;
const future = [
  { id: "child", title: "Появится ребёнок", icon: Baby }, { id: "new_job", title: "Новая работа", icon: BriefcaseBusiness },
  { id: "no_car", title: "Жизнь без машины", icon: Bus }, { id: "bigger_family", title: "Семья станет больше", icon: Users },
  { id: "relocation", title: "Возможен переезд", icon: MapPin }, { id: "longer_horizon", title: "Планирую надолго", icon: Clock3 },
] as const;
const pointTypes: { id: LifePoint["type"]; label: string }[] = [
  { id: "work", label: "Работа" }, { id: "school", label: "Школа" }, { id: "kindergarten", label: "Детский сад" },
  { id: "parents", label: "Родители" }, { id: "university", label: "Учёба" }, { id: "other", label: "Другое" },
];
const money = (value: number) => new Intl.NumberFormat("ru-RU").format(value);
const budgetBuy = [{ value: 5000000, label: "до 5 млн ₽" }, { value: 8000000, label: "5–8 млн ₽" }, { value: 12000000, label: "8–12 млн ₽" }, { value: 20000000, label: "12–20 млн ₽" }, { value: 25000000, label: "20+ млн ₽" }];
const budgetRent = [{ value: 20000, label: "до 20 тыс. ₽" }, { value: 35000, label: "20–35 тыс. ₽" }, { value: 55000, label: "35–55 тыс. ₽" }, { value: 70000, label: "55–70 тыс. ₽" }, { value: 90000, label: "70+ тыс. ₽" }];
function choose<T>(items: T[], item: T): T[] { return items.includes(item) ? items.filter((value) => value !== item) : [...items, item]; }
function payloadFromDraft(draft: OnboardingDraft) {
  const { commute_minutes: _commute, life_points, ...profile } = draft;
  void _commute;
  return { ...profile, name: draft.name.trim() || null, children_count: draft.children.length,
    purchase_budget: draft.housing_goal === "rent" ? null : draft.purchase_budget,
    initial_payment: draft.housing_goal === "rent" ? null : draft.initial_payment,
    comfortable_monthly_payment: draft.comfortable_monthly_payment || null,
    rent_budget: draft.housing_goal === "buy" ? null : draft.rent_budget,
    good_home_text: draft.good_home_text.trim() || null,
    partner: draft.household_type === "couple" ? { ...draft.partner, name: draft.partner.name || "Партнёр" } : null,
    life_points: life_points.filter((point) => draft.household_type === "couple" || point.owner_type === "primary_user").map(({ localId, ...point }) => { void localId; return point; }),
  };
}
function Pill({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" onClick={onClick} aria-pressed={selected} className={`focus-outline min-h-12 rounded-full border px-5 py-3 text-sm font-semibold transition ${selected ? "border-[#169b80] bg-[#daf8eb] text-[#126b5e]" : "border-[#d8e5e2] bg-white text-[#577078] hover:border-[#7ccbb7]"}`}>{children}</button>;
}
function Scale({ name, left, right, value, onChange }: { name: string; left: string; right: string; value: number | null; onChange: (value: number | null) => void }) {
  return <div className="rounded-[22px] border border-[#e0eae7] bg-white p-5 sm:p-6">
    <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-[#183c46]">{name}</h3><button type="button" onClick={() => onChange(null)} className="text-xs font-medium text-[#7a9695] underline">{value === null ? "Не выбрано" : "Сбросить"}</button></div>
    <div className="mt-5 grid grid-cols-5 gap-2">{[0, 25, 50, 75, 100].map((number) => <button key={number} type="button" onClick={() => onChange(number)} aria-label={`${name}: ${number} из 100`} aria-pressed={value === number}
      className={`focus-outline h-12 rounded-xl border transition ${value === number ? "border-[#23ae90] bg-[#37ba9b] shadow-[0_8px_20px_rgba(31,170,139,.25)]" : "border-[#dce9e5] bg-[#eff5f3] hover:bg-[#d6eee5]"}`} />)}</div>
    <div className="mt-3 flex justify-between text-xs text-[#718c91]"><span>{left}</span><span>{right}</span></div>
  </div>;
}
export default function OnboardingPage() {
  const router = useRouter();
  const { step, draft, setStep, patch, setPreference, upsertPoint, removePoint, setProfileId, reset } = useOnboarding();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [pointType, setPointType] = useState<LifePoint["type"]>("work");
  const [pointOwner, setPointOwner] = useState<LifePoint["owner_type"]>("primary_user");
  const [pointCoords, setPointCoords] = useState<Coordinates | null>(null);
  useEffect(() => setReady(true), []);
  function validate() {
    if (step === 2 && draft.housing_goal !== "rent" && draft.purchase_budget <= 0) return "Выберите бюджет покупки.";
    if (step === 2 && draft.housing_goal !== "buy" && draft.rent_budget <= 0) return "Выберите бюджет аренды.";
    if (step === 4 && draft.transport_preferences.length === 0) return "Выберите хотя бы один способ передвижения.";
    return "";
  }
  function next() { const message = validate(); if (message) { setError(message); return; } setError(""); setStep(step + 1); }
  function addPoint() {
    if (!pointCoords) { setError("Сначала коснитесь карты."); return; }
    const label = pointTypes.find((item) => item.id === pointType)?.label ?? "Место";
    const count = draft.life_points.filter((item) => item.type === pointType).length + 1;
    upsertPoint({ localId: crypto.randomUUID(), owner_type: pointOwner, type: pointType, name: `${label} ${count}`, ...pointCoords, importance: 7, frequency_per_week: pointType === "work" || pointType === "school" ? 5 : 2 });
    setPointCoords(null); setError("");
  }
  async function finish() {
    if (!draft.data_processing_consent) { setError("Для персонального анализа необходимо согласие на обработку данных."); return; }
    if (draft.data_processing_consent && ((draft.housing_goal !== "rent" && draft.purchase_budget <= 0) || (draft.housing_goal !== "buy" && draft.rent_budget <= 0))) {
      setStep(2); setError("Выберите бюджет для сохранения анкеты."); return;
    }
    setSaving(true); setError("");
    useAnalytics.getState().clear();
    useOnboarding.setState({ profileId: null });
    sessionStorage.removeItem("mesto-save-status");
    if (draft.data_processing_consent) {
      try {
        const endpoint = draft.household_type === "couple" ? "/api/couple/profile" : "/api/profile";
        const saved = await fetch(`${API_URL}${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payloadFromDraft(draft)) });
        if (!saved.ok) throw new Error(`Сервер вернул ${saved.status}`);
        const result = await saved.json();
        if (typeof result.id !== "string") throw new Error("Invalid profile response");
        setProfileId(result.id);
        try {
          const request = await fetch(`${API_URL}/api/analysis/request`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile_id: result.id }) });
          if (!request.ok) sessionStorage.setItem("mesto-save-status", `Запрос анализа не создан (HTTP ${request.status}). Выполняем расчёт оценки.`);
        } catch { sessionStorage.setItem("mesto-save-status", "Запрос анализа не создан. Выполняем расчёт оценки для сохранённого профиля."); }
      } catch { setError("Не удалось сохранить анкету. Проверьте соединение и попробуйте ещё раз."); setSaving(false); return; }
    }
    router.push("/analysis");
  }
  if (!ready) return <main className="page-shell grid place-items-center">Загрузка анкеты…</main>;
  const selectedPriorities = priorities.filter((item) => draft.preferences[item.id].is_answered).length;
  return <main className="page-shell min-h-screen bg-[#edf5f2] text-[#15323e]">
    <div className="bg-[#071b2a] text-white"><div className="content-shell flex h-20 items-center justify-between"><Brand /><div className="flex items-center gap-3"><span className="hidden text-xs text-[#9bb7ba] sm:inline">Красноярск · черновик сохраняется</span><span className="text-xs text-[#9bb7ba]">Создание сценария жизни</span></div></div></div>
    <div className="content-shell max-w-[1120px] pb-24 pt-8 sm:pt-12">
      <div className="mb-7 flex items-center justify-between gap-3 text-xs font-bold uppercase tracking-[.15em] text-[#507b7d]"><span>Ваш сценарий / {String(step + 1).padStart(2, "0")}</span><span>{Math.round((step + 1) * 10)}%</span></div>
      <div role="progressbar" aria-valuemin={1} aria-valuemax={10} aria-valuenow={step + 1} aria-label="Прогресс анкеты" className="mb-10 h-1.5 overflow-hidden rounded-full bg-[#d1e3dc]"><motion.div animate={{ width: `${(step + 1) * 10}%` }} transition={{ duration: .45 }} className="h-full rounded-full bg-[#22b493]" /></div>
      <div className="grid gap-8 lg:grid-cols-[1fr_270px] lg:gap-12"><div>
        <AnimatePresence mode="wait"><motion.section key={step} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: .26 }}>
          <p className="mb-3 text-xs font-bold uppercase tracking-[.2em] text-[#198f79]">Шаг {step + 1} из 10</p>
          <h1 className="max-w-[760px] text-[clamp(2.45rem,5vw,4.6rem)] font-semibold leading-[1.02] tracking-[-.065em]">{steps[step].title}</h1>
          <p className="mt-4 text-base text-[#6b8589]">{steps[step].caption}</p>
          <div className="mt-9">
            {step === 0 && <div className="grid gap-3 sm:grid-cols-2">{household.map((item, index) => <SelectionCard key={item.id} {...item} index={`0${index + 1}`} selected={draft.household_type === item.id} onClick={() => patch({ household_type: item.id, adults_count: item.id === "single" ? 1 : 2, partner: { ...draft.partner, name: item.id === "couple" ? "Партнёр" : "" } })} />)}</div>}
            {step === 1 && <div className="grid gap-3 sm:grid-cols-3">{goals.map((item, index) => <SelectionCard key={item.id} {...item} index={`0${index + 1}`} selected={draft.housing_goal === item.id} onClick={() => patch({ housing_goal: item.id })} />)}</div>}
            {step === 2 && <div className="space-y-7">{draft.housing_goal !== "rent" && <div><h2 className="mb-3 font-semibold">Покупка · до какой суммы?</h2><div className="flex flex-wrap gap-2">{budgetBuy.map((item) => <Pill key={item.value} selected={draft.purchase_budget === item.value} onClick={() => patch({ purchase_budget: item.value })}>{item.label}</Pill>)}</div></div>}{draft.housing_goal !== "buy" && <div><h2 className="mb-3 font-semibold">Аренда · в месяц</h2><div className="flex flex-wrap gap-2">{budgetRent.map((item) => <Pill key={item.value} selected={draft.rent_budget === item.value} onClick={() => patch({ rent_budget: item.value })}>{item.label}</Pill>)}</div></div>}<p className="text-xs leading-relaxed text-[#789196]">Для сохранения профиля диапазон передаётся как его верхний ориентир. Цены и доступность пока не рассчитываются.</p></div>}
            {step === 3 && <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">{[15, 30, 45, 60, 75].map((minutes) => <button key={minutes} type="button" onClick={() => patch({ commute_minutes: minutes })} aria-pressed={draft.commute_minutes === minutes} className={`focus-outline min-h-28 rounded-[22px] border text-center transition ${draft.commute_minutes === minutes ? "border-[#26b994] bg-[#dbf7eb] text-[#0d7564]" : "border-[#dce8e4] bg-white text-[#476b72] hover:border-[#8ecfbc]"}`}><Clock3 className="mx-auto mb-2" size={23} /><span className="text-2xl font-bold">{minutes === 75 ? "60+" : minutes}</span><span className="block text-xs">минут</span></button>)}</div>}
            {step === 4 && <div className="grid gap-3 sm:grid-cols-2">{transports.map((item) => <SelectionCard key={item.id} {...item} selected={draft.transport_preferences.includes(item.id)} onClick={() => patch({ transport_preferences: choose(draft.transport_preferences, item.id), car_availability: item.id === "car" ? !draft.transport_preferences.includes("car") : draft.car_availability })} />)}</div>}
            {step === 5 && <><div className="grid gap-3 sm:grid-cols-2">{priorities.map((item) => <SelectionCard key={item.id} title={item.title} icon={item.icon} selected={draft.preferences[item.id].is_answered} onClick={() => { if (!draft.preferences[item.id].is_answered && selectedPriorities >= 4) { setError("Можно выбрать до четырёх приоритетов."); return; } setError(""); setPreference(item.id, draft.preferences[item.id].is_answered ? null : item.value); }} />)}</div><p className="mt-4 text-sm text-[#719092]">Выбрано {selectedPriorities} из 4</p></>}
            {step === 6 && <div className="space-y-3"><Scale name="Ритм района" left="Тихий" right="Активный" value={draft.preferences.quiet_active.value} onChange={(value) => setPreference("quiet_active", value)} /><Scale name="Среда" left="Зелёная" right="Городская" value={draft.preferences.green_urban.value} onChange={(value) => setPreference("green_urban", value)} /><Scale name="Расположение" left="Ближе к центру" right="Спокойнее" value={draft.preferences.center_calm.value} onChange={(value) => setPreference("center_calm", value)} /></div>}
            {step === 7 && <div className="grid gap-3 sm:grid-cols-2">{future.map((item) => <SelectionCard key={item.id} title={item.title} icon={item.icon} selected={draft.future_changes.includes(item.id)} onClick={() => patch({ future_changes: choose(draft.future_changes, item.id) })} />)}<SelectionCard title="Пока не знаю" icon={Sparkles} selected={draft.future_changes.length === 0} onClick={() => patch({ future_changes: [] })} /></div>}
            {step === 8 && <div className="space-y-5"><div className="flex flex-wrap gap-2">{pointTypes.map((item) => <Pill key={item.id} selected={pointType === item.id} onClick={() => setPointType(item.id)}>{item.label}</Pill>)}</div>{draft.household_type === "couple" && <div className="flex gap-2"><Pill selected={pointOwner === "primary_user"} onClick={() => setPointOwner("primary_user")}>Моё место</Pill><Pill selected={pointOwner === "partner"} onClick={() => setPointOwner("partner")}>Партнёра</Pill></div>}<LifePointMap value={pointCoords} onChange={setPointCoords} /><div className="flex items-center justify-between gap-3"><span className="text-xs text-[#759293]">Красноярск · нажмите на карту</span><button type="button" onClick={addPoint} className="rounded-full bg-[#123948] px-5 py-3 text-sm font-semibold text-white">Добавить точку</button></div>{draft.life_points.length > 0 && <div className="space-y-2">{draft.life_points.map((point) => <div key={point.localId} className="flex items-center justify-between rounded-2xl border border-[#dce9e5] bg-white px-5 py-3 text-sm"><span><MapPin size={15} className="mr-2 inline text-[#19a489]" />{point.name}</span><button type="button" onClick={() => removePoint(point.localId)} aria-label={`Удалить ${point.name}`}><X size={17} /></button></div>)}</div>}</div>}
            {step === 9 && <div className="space-y-5"><div className="grid gap-3 sm:grid-cols-2">{[["Кто", household.find((item) => item.id === draft.household_type)?.title], ["Цель", goals.find((item) => item.id === draft.housing_goal)?.title], ["Покупка", draft.housing_goal === "rent" ? "—" : `${money(draft.purchase_budget)} ₽`], ["Аренда / мес", draft.housing_goal === "buy" ? "—" : `${money(draft.rent_budget)} ₽`], ["Дорога", draft.commute_minutes ? (draft.commute_minutes === 75 ? "60+ мин" : `до ${draft.commute_minutes} мин`) : "Не указано"], ["Транспорт", draft.transport_preferences.map((value) => transports.find((item) => item.id === value)?.title).join(", ")], ["Приоритеты", priorities.filter((item) => draft.preferences[item.id].is_answered).map((item) => item.title).join(", ") || "Не выбраны"], ["Важные места", `${draft.life_points.length}`]].map(([label, value]) => <div key={label} className="rounded-[20px] border border-[#dce9e5] bg-white p-5"><span className="text-xs font-semibold uppercase tracking-[.13em] text-[#7b9697]">{label}</span><p className="mt-2 text-lg font-semibold">{value}</p></div>)}</div><label className="flex cursor-pointer items-start gap-3 rounded-[20px] border border-[#dce9e5] bg-white p-5 text-sm leading-relaxed text-[#466771]"><input type="checkbox" checked={draft.data_processing_consent} onChange={(event) => patch({ data_processing_consent: event.target.checked })} className="mt-1 h-5 w-5 accent-[#139b7b]" /><span>Согласен(на) на сохранение анкеты и обработку ответов для персонального анализа.</span></label><p className="text-xs leading-relaxed text-[#799498]">Для персональной оценки нужно сохранить анкету. Без согласия можно <Link href="/district" className="underline">посмотреть карту районов</Link>.</p></div>}
          </div>
        </motion.section></AnimatePresence>
        {error && <p role="alert" className="mt-5 rounded-2xl bg-[#fff0ec] p-4 text-sm font-semibold text-[#ad4d37]">{error}</p>}
        <div className="mt-9 flex items-center justify-between gap-3 border-t border-[#d5e5df] pt-6"><button type="button" disabled={step === 0} onClick={() => { setError(""); setStep(step - 1); }} className="inline-flex min-h-12 items-center gap-2 rounded-full px-4 text-sm font-semibold text-[#436a70] disabled:opacity-30"><ArrowLeft size={17} /> Назад</button>{step < 9 ? <button type="button" onClick={next} className="inline-flex min-h-14 items-center gap-2 rounded-full bg-[#0f3543] px-7 text-sm font-bold text-white transition hover:bg-[#18685f]">Продолжить <ArrowRight size={17} /></button> : <button type="button" onClick={finish} disabled={saving} className="inline-flex min-h-14 items-center gap-2 rounded-full bg-[#0f9c7d] px-7 text-sm font-bold text-white disabled:opacity-60">{saving ? "Сохраняем…" : "Показать моё место"} <ArrowRight size={17} /></button>}</div>
      </div><aside className="hidden lg:block"><div className="sticky top-8 rounded-[27px] bg-[#0b2c3a] p-6 text-white"><span className="text-xs font-bold uppercase tracking-[.2em] text-[#9eebd5]">Ваш маршрут</span><div className="mt-7 space-y-2">{steps.map((item, index) => <button key={item.title} type="button" onClick={() => { setError(""); setStep(index); }} disabled={index > step} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs transition ${index === step ? "bg-white/10 text-white" : "text-[#83a8ad] hover:bg-white/5 disabled:cursor-default disabled:hover:bg-transparent"}`}><span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full ${index < step ? "bg-[#9cebd4] text-[#0c3440]" : "border border-white/20"}`}>{index < step ? <Check size={13} /> : index + 1}</span>{item.title}</button>)}</div></div><button type="button" onClick={() => { reset(); setError(""); }} className="mt-4 flex items-center gap-2 text-xs font-medium text-[#718f92]"><RotateCcw size={14} /> Начать заново</button></aside></div>
    </div>
  </main>;
}
