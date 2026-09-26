"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowLeft, ArrowRight, MapPin, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { type Coordinates, type LifePoint, type OnboardingDraft,
  type WeightName, useOnboarding, weightNames } from "@/lib/onboarding-store";

const LifePointMap = dynamic(() => import("@/components/life-point-map"), { ssr: false });
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const titles = [
  "Для кого ищем место?", "Кто будет жить?", "Покупка или аренда?", "Ваш бюджет",
  "Ваши ежедневные маршруты", "Что важно рядом?", "Ваш стиль жизни",
  "Готовность к компромиссам", "Что может измениться?", "Что означает хороший дом?",
];

const householdOptions = [
  ["single", "Для себя"], ["couple", "Для пары"], ["family", "Для семьи"],
  ["family_with_relatives", "Для семьи с родственниками"],
] as const;
const transportOptions = [
  ["car", "Автомобиль"], ["public_transport", "Общественный транспорт"],
  ["walking", "Пешком"], ["bicycle", "Велосипед"],
] as const;
const pointTypes = [
  ["work", "Работа"], ["partner_work", "Работа партнёра"], ["school", "Школа"],
  ["kindergarten", "Детский сад"], ["parents", "Родители"],
  ["university", "Университет"], ["other", "Другое"],
] as const;
const weightLabels: Record<WeightName, string> = {
  education_weight: "Школы", kindergarten_weight: "Детские сады", healthcare_weight: "Медицина",
  transport_weight: "Транспорт", ecology_weight: "Экология", safety_weight: "Безопасность",
  parks_weight: "Парки", shopping_weight: "Магазины", entertainment_weight: "Досуг",
  housing_price_weight: "Цена жилья", future_growth_weight: "Развитие района",
};
const futureOptions = [
  ["child", "Рождение ребёнка"], ["new_job", "Новая работа"], ["no_car", "Жизнь без автомобиля"],
  ["bigger_family", "Семья станет больше"], ["relocation", "Переезд"],
  ["longer_horizon", "Долгий горизонт"],
] as const;
const valueOptions = [
  ["family_time", "Больше времени с семьёй"], ["calm", "Спокойствие"],
  ["financial_stability", "Финансовая устойчивость"], ["mobility", "Мобильность"],
  ["green_environment", "Зелёная среда"], ["district_growth", "Развитие района"],
  ["nearby_infrastructure", "Инфраструктура рядом"], ["personal_space", "Личное пространство"],
] as const;

function Choice({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" onClick={onClick} aria-pressed={selected}
    className={`rounded-2xl border px-4 py-3 text-left font-medium transition ${selected ? "border-teal-600 bg-teal-50 text-teal-900 ring-1 ring-teal-600" : "border-slate-200 bg-white hover:border-teal-400"}`}>
    {children}
  </button>;
}

function NumberField({ label, value, onChange, min = 0, max, step = 1 }: { label: string; value: number; onChange: (value: number) => void; min?: number; max?: number; step?: number }) {
  return <label className="block text-sm font-medium text-slate-700">{label}
    <input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))}
      className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-navy focus:border-teal-600 focus:outline-none" />
  </label>;
}

function Slider({ label, value, onChange, left, right }: { label: string; value: number; onChange: (value: number) => void; left?: string; right?: string }) {
  return <label className="block rounded-xl border border-slate-200 bg-white p-4">
    <span className="flex justify-between gap-3 text-sm font-semibold"><span>{label}</span><span>{value}/100</span></span>
    <input aria-label={label} type="range" min="0" max="100" value={value}
      onChange={(event) => onChange(Number(event.target.value))} className="mt-3 w-full accent-teal-600" />
    {(left || right) && <span className="flex justify-between text-xs text-slate-500"><span>{left}</span><span>{right}</span></span>}
  </label>;
}

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function payloadFromDraft(draft: OnboardingDraft) {
  const partnerWork = draft.life_points.find((point) => point.type === "partner_work");
  return {
    ...draft,
    name: draft.name.trim() || null,
    children_count: draft.children.length,
    purchase_budget: draft.housing_goal === "rent" ? null : draft.purchase_budget,
    initial_payment: draft.housing_goal === "rent" ? null : draft.initial_payment,
    comfortable_monthly_payment: draft.comfortable_monthly_payment || null,
    rent_budget: draft.housing_goal === "buy" ? null : draft.rent_budget,
    good_home_text: draft.good_home_text.trim() || null,
    partner: draft.partner.name.trim() ? { ...draft.partner,
      work_point: partnerWork ? { latitude: partnerWork.latitude, longitude: partnerWork.longitude } : draft.partner.work_point } : null,
    life_points: draft.life_points.map(({ localId, ...point }) => point),
  };
}

export default function OnboardingPage() {
  const { step, draft, profileId, setStep, patch, setPreference, upsertPoint, removePoint, fillDemo, setProfileId, reset } = useOnboarding();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [requestStatus, setRequestStatus] = useState("");
  const [pointId, setPointId] = useState<string | null>(null);
  const [pointType, setPointType] = useState<LifePoint["type"]>("work");
  const [pointName, setPointName] = useState("");
  const [pointCoords, setPointCoords] = useState<Coordinates | null>(null);
  const [pointImportance, setPointImportance] = useState(5);
  const [pointFrequency, setPointFrequency] = useState(5);

  useEffect(() => { setReady(true); }, []);
  useEffect(() => { setRequestStatus(""); }, [draft]);

  function resetPointForm() {
    setPointId(null); setPointType("work"); setPointName(""); setPointCoords(null);
    setPointImportance(5); setPointFrequency(5);
  }

  function editPoint(point: LifePoint) {
    setPointId(point.localId); setPointType(point.type); setPointName(point.name);
    setPointCoords({ longitude: point.longitude, latitude: point.latitude });
    setPointImportance(point.importance); setPointFrequency(point.frequency_per_week);
    setError("");
  }

  function savePoint() {
    if (!pointName.trim() || !pointCoords) { setError("Укажите название и точку на карте."); return; }
    if (pointCoords.latitude < -90 || pointCoords.latitude > 90 || pointCoords.longitude < -180 || pointCoords.longitude > 180) {
      setError("Координаты должны быть в диапазоне широта −90…90, долгота −180…180."); return;
    }
    if (pointImportance < 1 || pointImportance > 10 || pointFrequency < 0 || pointFrequency > 7) {
      setError("Важность: 1–10, поездок в неделю: 0–7."); return;
    }
    upsertPoint({ localId: pointId ?? crypto.randomUUID(), type: pointType, name: pointName.trim(),
      ...pointCoords, importance: pointImportance, frequency_per_week: pointFrequency });
    resetPointForm(); setError("");
  }

  function validateStep(): string {
    if (step === 1) {
      if (draft.adults_count < 1 || draft.adults_count > 12) return "Укажите число взрослых от 1 до 12.";
      if (draft.household_type === "couple" && (draft.adults_count < 2 || !draft.partner.name.trim()))
        return "Для пары нужны два взрослых и имя партнёра.";
      if (draft.children.some(({ age }) => age < 0 || age > 17)) return "Возраст ребёнка должен быть от 0 до 17 лет.";
    }
    if (step === 3) {
      if (draft.housing_goal !== "rent" && draft.purchase_budget <= 0) return "Укажите бюджет покупки больше нуля.";
      if (draft.housing_goal !== "buy" && draft.rent_budget <= 0) return "Укажите бюджет аренды больше нуля.";
      if (draft.initial_payment < 0 || draft.initial_payment > draft.purchase_budget && draft.housing_goal !== "rent")
        return "Первоначальный взнос должен быть не больше бюджета покупки.";
    }
    if (step === 4 && draft.life_points.length === 0) return "Добавьте хотя бы одно важное место.";
    if (step === 6 && (!draft.transport_preferences.length || draft.partner.name.trim() && !draft.partner.transport_preferences.length))
      return "Выберите хотя бы один способ передвижения для каждого человека.";
    if (step === 9 && !draft.data_processing_consent) return "Подтвердите согласие на обработку данных.";
    return "";
  }

  function next() {
    const problem = validateStep();
    if (problem) { setError(problem); return; }
    setError(""); setStep(step + 1);
  }

  async function submit() {
    const problem = validateStep();
    if (problem) { setError(problem); return; }
    setSaving(true); setError("");
    try {
      let id = profileId;
      if (!id) {
        const endpoint = draft.household_type === "couple" ? "/api/couple/profile" : "/api/profile";
        const response = await fetch(`${API_URL}${endpoint}`, { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify(payloadFromDraft(draft)) });
        if (!response.ok) throw new Error(`Не удалось сохранить анкету (${response.status}). Проверьте заполненные поля.`);
        id = (await response.json()).id as string;
        setProfileId(id);
      }
      const response = await fetch(`${API_URL}/api/analysis/request`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile_id: id }) });
      if (!response.ok) throw new Error(`Анкета сохранена, но запрос не создан (${response.status}). Попробуйте ещё раз.`);
      setRequestStatus("Анкета сохранена. Запрос принят; расчёт результатов появится на следующем этапе.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось связаться с сервером.");
    } finally { setSaving(false); }
  }

  if (!ready) return <main className="mx-auto max-w-3xl px-6 py-16">Загрузка анкеты…</main>;

  return <main className="min-h-screen bg-[#f4f8f6] px-4 py-8 text-slate-900 sm:px-6">
    <div className="mx-auto max-w-4xl">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2 text-xl font-black text-slate-900"><MapPin className="text-teal-700" />МЕСТО</Link>
        <div className="flex gap-2">
          <button type="button" onClick={() => { fillDemo(); setError(""); setRequestStatus(""); }} className="rounded-xl border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-800 hover:bg-teal-50">Заполнить демо</button>
          <button type="button" onClick={() => { reset(); setError(""); setRequestStatus(""); resetPointForm(); }} className="flex items-center gap-1 rounded-xl px-3 py-2 text-sm text-slate-600 hover:bg-white"><RotateCcw size={15} /> Сбросить</button>
        </div>
      </header>

      <div className="mb-5 flex items-center justify-between text-sm font-medium text-slate-600"><span>Шаг {step + 1} из 10</span><span>Ваш черновик сохраняется в этом браузере</span></div>
      <div className="mb-8 h-2 rounded-full bg-slate-200" role="progressbar" aria-valuenow={step + 1} aria-valuemin={1} aria-valuemax={10}>
        <div className="h-full rounded-full bg-teal-600 transition-all" style={{ width: `${(step + 1) * 10}%` }} />
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-10">
        <p className="mb-2 text-sm font-bold uppercase tracking-widest text-teal-700">Ваш жизненный сценарий</p>
        <h1 className="mb-2 text-3xl font-bold tracking-tight sm:text-4xl">{titles[step]}</h1>
        <p className="mb-8 text-slate-600">Ответьте на один вопрос за раз. Вы сможете вернуться и изменить ответ.</p>

        {step === 0 && <div className="grid gap-3 sm:grid-cols-2">{householdOptions.map(([value, label]) =>
          <Choice key={value} selected={draft.household_type === value} onClick={() => patch({ household_type: value,
            adults_count: value === "single" ? 1 : Math.max(2, draft.adults_count) })}>{label}</Choice>)}</div>}

        {step === 1 && <div className="grid gap-5 sm:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700">Ваше имя (необязательно)
            <input value={draft.name} onChange={(event) => patch({ name: event.target.value })} maxLength={120}
              className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-base" placeholder="Как к вам обращаться" /></label>
          <NumberField label="Взрослых" value={draft.adults_count} min={1} onChange={(adults_count) => patch({ adults_count })} />
          <NumberField label="Детей" value={draft.children.length} onChange={(count) => patch({ children: Array.from({ length: Math.max(0, Math.min(12, count)) }, (_, index) => draft.children[index] ?? { age: 0 }) })} />
          {(draft.household_type === "couple" || draft.household_type === "family") && <label className="block text-sm font-medium text-slate-700">Имя партнёра{draft.household_type === "couple" ? " *" : ""}
            <input value={draft.partner.name} onChange={(event) => patch({ partner: { ...draft.partner, name: event.target.value } })} maxLength={120}
              className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-base" placeholder="Например, Анна" /></label>}
          {draft.children.map((child, index) => <NumberField key={index} label={`Возраст ребёнка ${index + 1}`} value={child.age}
            onChange={(age) => patch({ children: draft.children.map((item, position) => position === index ? { age } : item) })} />)}
        </div>}

        {step === 2 && <div className="grid gap-3 sm:grid-cols-3">{([
          ["buy", "Покупка"], ["rent", "Аренда"], ["compare", "Хочу сравнить"],
        ] as const).map(([value, label]) => <Choice key={value} selected={draft.housing_goal === value}
          onClick={() => patch({ housing_goal: value })}>{label}</Choice>)}</div>}

        {step === 3 && <div className="grid gap-5 sm:grid-cols-2">
          {draft.housing_goal !== "rent" && <><NumberField label="Бюджет покупки, ₽" value={draft.purchase_budget} onChange={(purchase_budget) => patch({ purchase_budget })} />
            <NumberField label="Первоначальный взнос, ₽" value={draft.initial_payment} onChange={(initial_payment) => patch({ initial_payment })} />
            <NumberField label="Комфортный платёж в месяц, ₽" value={draft.comfortable_monthly_payment} onChange={(comfortable_monthly_payment) => patch({ comfortable_monthly_payment })} /></>}
          {draft.housing_goal !== "buy" && <NumberField label="Бюджет аренды в месяц, ₽" value={draft.rent_budget} onChange={(rent_budget) => patch({ rent_budget })} />}
          <label className="block text-sm font-medium text-slate-700">На какой срок планируете?
            <select value={draft.planning_horizon} onChange={(event) => patch({ planning_horizon: event.target.value as OnboardingDraft["planning_horizon"] })}
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base">
              <option value="1_2_years">1–2 года</option><option value="3_5_years">3–5 лет</option>
              <option value="5_10_years">5–10 лет</option><option value="long_term">Долгосрочно</option>
            </select></label>
        </div>}

        {step === 4 && <div className="space-y-6">
          <p className="text-sm text-slate-600">Поставьте точку на карте или перетащите маркер. Координаты можно уточнить вручную.</p>
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="block text-sm font-medium">Тип места<select value={pointType} onChange={(event) => setPointType(event.target.value as LifePoint["type"])} className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3">{pointTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="block text-sm font-medium">Название<input value={pointName} onChange={(event) => setPointName(event.target.value)} maxLength={120} placeholder="Например, работа Максима" className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3" /></label>
          </div>
          <LifePointMap value={pointCoords} onChange={setPointCoords} />
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField label="Широта" value={pointCoords?.latitude ?? 0} min={-90} step={0.000001} onChange={(latitude) => setPointCoords({ latitude, longitude: pointCoords?.longitude ?? 92.87 })} />
            <NumberField label="Долгота" value={pointCoords?.longitude ?? 0} min={-180} step={0.000001} onChange={(longitude) => setPointCoords({ latitude: pointCoords?.latitude ?? 56.01, longitude })} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField label="Важность места (1–10)" value={pointImportance} min={1} max={10} onChange={setPointImportance} />
            <NumberField label="Поездок в неделю" value={pointFrequency} max={7} onChange={setPointFrequency} />
          </div>
          <div className="flex flex-wrap gap-3"><button type="button" onClick={savePoint} className="rounded-xl bg-teal-700 px-5 py-3 font-semibold text-white hover:bg-teal-800">{pointId ? "Сохранить изменения" : "Добавить место"}</button>
            {pointId && <button type="button" onClick={resetPointForm} className="rounded-xl border px-5 py-3">Отмена</button>}</div>
          <div className="space-y-2">{draft.life_points.map((point) => <div key={point.localId} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 text-sm">
            <span><strong>{point.name}</strong> · {point.frequency_per_week} дней/неделю · важность {point.importance}/10</span>
            <span className="flex gap-2"><button type="button" onClick={() => editPoint(point)} className="font-semibold text-teal-700">Изменить</button><button type="button" onClick={() => removePoint(point.localId)} className="text-rose-700">Удалить</button></span>
          </div>)}</div>
        </div>}

        {step === 5 && <div className="space-y-5">
          <p className="text-sm text-slate-600">Оцените каждый фактор от 0 до 100. Ваши предпочтения и предпочтения партнёра хранятся отдельно.</p>
          <div className="grid gap-3 sm:grid-cols-2">{weightNames.map((name) => <Slider key={name} label={weightLabels[name]} value={draft.preferences[name]} onChange={(value) => setPreference(name, value)} />)}</div>
          {draft.partner.name.trim() && <div className="rounded-2xl bg-teal-50 p-5"><h2 className="mb-4 text-lg font-bold">Что важно {draft.partner.name}?</h2>
            <div className="grid gap-3 sm:grid-cols-3">{(["education_weight", "parks_weight", "ecology_weight"] as const).map((name) =>
              <Slider key={name} label={weightLabels[name]} value={draft.partner.preferences[name] ?? 50} onChange={(value) => patch({ partner: { ...draft.partner, preferences: { ...draft.partner.preferences, [name]: value } } })} />)}</div></div>}
        </div>}

        {step === 6 && <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <Slider label="Ритм района" left="Тихий" right="Активный" value={draft.preferences.quiet_active} onChange={(value) => setPreference("quiet_active", value)} />
            <Slider label="Среда" left="Зелёная" right="Городская" value={draft.preferences.green_urban} onChange={(value) => setPreference("green_urban", value)} />
            <Slider label="Расположение" left="Центр" right="Спокойный район" value={draft.preferences.center_calm} onChange={(value) => setPreference("center_calm", value)} />
          </div>
          <label className="flex items-center gap-3 font-medium"><input type="checkbox" checked={draft.car_availability} onChange={(event) => patch({ car_availability: event.target.checked })} className="h-5 w-5 accent-teal-700" />У меня есть автомобиль</label>
          <div><p className="mb-3 font-semibold">Как вы передвигаетесь?</p><div className="grid gap-2 sm:grid-cols-2">{transportOptions.map(([value, label]) => <Choice key={value} selected={draft.transport_preferences.includes(value)} onClick={() => patch({ transport_preferences: toggle(draft.transport_preferences, value) })}>{label}</Choice>)}</div></div>
          {draft.partner.name.trim() && <div><p className="mb-3 font-semibold">Транспорт партнёра</p><div className="grid gap-2 sm:grid-cols-2">{transportOptions.map(([value, label]) => <Choice key={value} selected={draft.partner.transport_preferences.includes(value)} onClick={() => patch({ partner: { ...draft.partner, transport_preferences: toggle(draft.partner.transport_preferences, value) } })}>{label}</Choice>)}</div></div>}
        </div>}

        {step === 7 && <div className="grid gap-4">
          <Slider label="Цена или время в пути" left="Ниже цена" right="Короче дорога" value={draft.price_vs_time} onChange={(price_vs_time) => patch({ price_vs_time })} />
          <Slider label="Сегодня или будущее района" left="Удобно сейчас" right="Потенциал развития" value={draft.today_vs_future} onChange={(today_vs_future) => patch({ today_vs_future })} />
          <Slider label="Зависимость от автомобиля" left="Можно без машины" right="Машина нужна" value={draft.car_dependency} onChange={(car_dependency) => patch({ car_dependency })} />
        </div>}

        {step === 8 && <div className="grid gap-3 sm:grid-cols-2">{futureOptions.map(([value, label]) => <Choice key={value} selected={draft.future_changes.includes(value)} onClick={() => patch({ future_changes: toggle(draft.future_changes, value) })}>{label}</Choice>)}</div>}

        {step === 9 && <div className="space-y-6">
          <div><p className="mb-3 font-semibold">Выберите не больше трёх ценностей ({draft.home_values.length}/3)</p><div className="grid gap-3 sm:grid-cols-2">{valueOptions.map(([value, label]) => <Choice key={value} selected={draft.home_values.includes(value)} onClick={() => {
            if (!draft.home_values.includes(value) && draft.home_values.length >= 3) { setError("Можно выбрать не больше трёх ценностей."); return; }
            setError(""); patch({ home_values: toggle(draft.home_values, value) });
          }}>{label}</Choice>)}</div></div>
          <label className="block font-medium">Опишите хороший дом своими словами (необязательно)
            <textarea value={draft.good_home_text} onChange={(event) => patch({ good_home_text: event.target.value })} maxLength={2000} rows={4}
              className="mt-2 w-full rounded-xl border border-slate-300 p-4" placeholder="Что должно измениться в вашей повседневной жизни?" /></label>
          <label className="flex items-start gap-3 rounded-xl bg-slate-50 p-4 text-sm"><input type="checkbox" checked={draft.data_processing_consent}
            onChange={(event) => patch({ data_processing_consent: event.target.checked })} className="mt-0.5 h-5 w-5 accent-teal-700" />
            <span>Согласен(на) на обработку данных анкеты для сохранения профиля и создания запроса на анализ.</span></label>
          <p className="text-sm text-slate-500">Расчёт рекомендаций пока не выполняется. Анкета и запрос сохраняются для следующего этапа.</p>
        </div>}

        {error && <p role="alert" className="mt-6 rounded-xl bg-rose-50 p-4 text-sm font-semibold text-rose-800">{error}</p>}
        {requestStatus && <div role="status" className="mt-6 rounded-xl bg-teal-50 p-5 text-teal-900"><p className="font-bold">{requestStatus}</p><p className="mt-2 break-all text-sm">ID профиля: {profileId}</p></div>}

        <div className="mt-9 flex items-center justify-between gap-3 border-t border-slate-200 pt-6">
          <button type="button" onClick={() => { setError(""); setStep(step - 1); }} disabled={step === 0}
            className="flex items-center gap-2 rounded-xl px-4 py-3 font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40"><ArrowLeft size={18} /> Назад</button>
          {step < 9 ? <button type="button" onClick={next} className="flex items-center gap-2 rounded-xl bg-slate-900 px-6 py-3 font-semibold text-white hover:bg-slate-700">Дальше <ArrowRight size={18} /></button>
            : <button type="button" onClick={submit} disabled={saving || Boolean(requestStatus)} className="rounded-xl bg-teal-700 px-6 py-3 font-semibold text-white hover:bg-teal-800 disabled:opacity-50">{saving ? "Сохраняем…" : requestStatus ? "Запрос создан" : "Сохранить и создать запрос"}</button>}
        </div>
      </section>
    </div>
  </main>;
}
