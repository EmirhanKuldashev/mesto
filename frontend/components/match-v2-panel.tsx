"use client";

import { useEffect, useMemo, useState } from 'react';
import type { Complex } from '@/lib/complex-scoring';
import type { LocalLocation } from '@/types/local';
import type { DestinationKind, TravelMode } from '@/types/mobility';
import type { Importance, InfrastructureImportance, MatchRequest, MatchResult } from '@/types/match-v2';
import { calculateMatch } from '@/lib/api/match-v2';

const labels = { stop: 'Остановки', school: 'Школы', kindergarten: 'Детские сады', healthcare: 'Медицина', parks: 'Парки' };
const importanceLabels = ['Не важно','Немного важно','Важно','Очень важно'];
const input = 'mt-1 w-full min-w-0 rounded-xl border border-[#cadbd5] bg-white px-3 py-2 text-sm';
type DraftDestination = { label: string; kind: DestinationKind; latitude: string; longitude: string; importance: Importance; threshold: string };

export function MatchV2Panel({ location, complexes, onSelect }: { location: LocalLocation | null; complexes: Complex[]; onSelect: (p: LocalLocation) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [importance, setImportance] = useState<InfrastructureImportance>({ stop: null, school: null, kindergarten: null, healthcare: null, parks: null });
  const [mode, setMode] = useState<TravelMode>('car');
  const [destinations, setDestinations] = useState<DraftDestination[]>([]);
  const [budget, setBudget] = useState('');
  const [marketId, setMarketId] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState<Omit<MatchRequest,'candidate'> | null>(null);
  const [result, setResult] = useState<{ key: string; value: MatchResult } | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const request = useMemo(() => location && submitted ? { candidate: location, ...submitted } : null, [location,submitted]);
  const key = request ? JSON.stringify(request) : '';
  const matching = complexes.find(c => c.id === marketId && c.location?.coordinates[0] === location?.longitude && c.location?.coordinates[1] === location?.latitude);
  const invalidate = () => setSubmitted(null);
  const changeDestination = (index: number, change: Partial<DraftDestination>) => { invalidate(); setDestinations(rows => rows.map((d,i) => i === index ? { ...d,...change } : d)); };
  useEffect(() => {
    if (!request) return;
    const controller = new AbortController(); let active = true;
    const timeout = setTimeout(() => controller.abort(), 35000);
    setLoading(key); setError(null);
    calculateMatch(request,controller.signal).then(value => { if (active) setResult({ key,value }); })
      .catch(cause => { if (active) setError({ key,message: controller.signal.aborted ? 'Расчёт занял слишком много времени. Повторите попытку.' : cause instanceof Error ? cause.message : 'Не удалось выполнить расчёт.' }); })
      .finally(() => { if (active) setLoading(null); clearTimeout(timeout); });
    return () => { active = false; controller.abort(); clearTimeout(timeout); };
  }, [request,key,attempt]);
  const current = result?.key === key && key ? result.value : null;
  const fit = current?.personal_fit.infrastructure;
  return <section aria-label="Ваши приоритеты" className="min-w-0 rounded-[26px] border border-[#dbe8e4] bg-white p-5">
    <h2 className="text-lg font-semibold">Подходит вашим приоритетам</h2>
    <p className="mt-2 text-xs leading-relaxed text-[#607f82]">Экспериментальная оценка инфраструктуры. MESTO Local остаётся отдельной объективной оценкой места. Общий Match пока не рассчитывается.</p>
    <button type="button" aria-expanded={expanded} onClick={() => setExpanded(v => !v)} className="mt-3 text-sm font-semibold text-[#087e75]">{expanded ? 'Скрыть настройки' : 'Настроить приоритеты'}</button>
    {expanded && <form className="mt-4 space-y-4" onSubmit={event => {
      event.preventDefault();
      setSubmitted({ profile: { infrastructure: importance, purchase_budget: budget === '' ? null : Number(budget),
        mobility: destinations.length ? { preferred_mode: mode, destinations: destinations.map(d => ({ latitude: Number(d.latitude),longitude: Number(d.longitude),
          label: d.label,kind: d.kind,importance: d.importance,max_acceptable_minutes: d.threshold === '' ? null : Number(d.threshold) })) } : null },market_candidate_id: matching?.id ?? null });
      setAttempt(v => v + 1);
    }}>
      {!location && <p className="text-sm text-[#76562b]">Выберите место в MESTO Local или на карте.</p>}
      <fieldset className="space-y-2"><legend className="mb-2 text-sm font-semibold">Что важно рядом</legend>
        {(Object.keys(labels) as (keyof InfrastructureImportance)[]).map(k => <label key={k} className="block text-xs">{labels[k]}<select aria-label={`Важность: ${labels[k]}`} className={input} value={importance[k] ?? ''} onChange={e => { invalidate(); setImportance(v => ({ ...v,[k]: e.target.value === '' ? null : Number(e.target.value) as Importance })); }}>
          <option value="">Не указано</option>{importanceLabels.map((label,i) => <option value={i} key={i}>{label}</option>)}</select></label>)}
      </fieldset>
      <details><summary className="cursor-pointer text-sm font-semibold">Поездки и бюджет — необязательно</summary>
        <div className="mt-3 space-y-3">
          <label className="block text-xs">Транспорт<select aria-label="Транспорт для предпочтений" className={input} value={mode} onChange={e => { invalidate(); setMode(e.target.value as TravelMode); }}><option value="car">На машине</option><option value="public_transport">Общественный транспорт — пока недоступен</option></select></label>
          {destinations.map((d,i) => <fieldset key={i} className="min-w-0 space-y-2 rounded-xl border border-[#dbe8e4] p-3"><legend className="text-xs">Важное место {i+1}</legend>
            <label className="block text-xs">Название<input aria-label={`Название поездки ${i+1}`} required maxLength={80} className={input} value={d.label} onChange={e => changeDestination(i,{ label: e.target.value })} /></label>
            <label className="block text-xs">Тип<select aria-label={`Тип поездки ${i+1}`} className={input} value={d.kind} onChange={e => changeDestination(i,{ kind: e.target.value as DestinationKind })}>{Object.entries({ work:'Работа',university:'Университет',school:'Школа',relatives:'Родственники',other:'Другое' }).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <div className="grid min-w-0 grid-cols-2 gap-2"><label className="min-w-0 text-xs">Широта<input aria-label={`Широта поездки ${i+1}`} className={input} required type="number" step="any" min="-90" max="90" value={d.latitude} onChange={e => changeDestination(i,{ latitude:e.target.value })} /></label><label className="min-w-0 text-xs">Долгота<input aria-label={`Долгота поездки ${i+1}`} className={input} required type="number" step="any" min="-180" max="180" value={d.longitude} onChange={e => changeDestination(i,{ longitude:e.target.value })} /></label></div>
            <label className="block text-xs">Важность<select aria-label={`Важность поездки ${i+1}`} className={input} value={d.importance} onChange={e => changeDestination(i,{ importance:Number(e.target.value) as Importance })}>{importanceLabels.map((v,k) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="block text-xs">Допустимое время, мин<input aria-label={`Допустимое время поездки ${i+1}`} className={input} type="number" min="0.1" max="1440" step="any" value={d.threshold} onChange={e => changeDestination(i,{ threshold:e.target.value })} /></label>
            <button type="button" className="text-xs underline" onClick={() => { invalidate(); setDestinations(rows => rows.filter((_,n) => n!==i)); }}>Удалить место {i+1}</button>
          </fieldset>)}
          {destinations.length < 5 && <button type="button" className="text-sm text-[#087e75] underline" onClick={() => { invalidate(); setDestinations(rows => [...rows,{ label:'',kind:'work',latitude:'',longitude:'',importance:2,threshold:'' }]); }}>Добавить поездку</button>}
          <label className="block text-xs">Бюджет покупки, ₽<input aria-label="Бюджет покупки для места" className={input} type="number" min="1" step="any" value={budget} onChange={e => { invalidate(); setBudget(e.target.value); }} /></label>
          <label className="block text-xs">ЖК для проверки стартовой цены<select aria-label="ЖК для проверки бюджета" className={input} value={matching?.id ?? ''} onChange={e => {
            invalidate(); const complex=complexes.find(c => c.id===Number(e.target.value)); setMarketId(complex?.id ?? null);
            if (complex?.location) onSelect({ longitude:complex.location.coordinates[0],latitude:complex.location.coordinates[1] });
          }}><option value="">Без привязки к ЖК</option>{complexes.filter(c => c.source_id==='cian' && !c.is_synthetic && c.location).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <p className="text-xs text-[#607f82]">Выбор ЖК переносит точку на координату источника. Это ориентир на карте, не проверенный корпус или вход. Стартовая цена не гарантирует наличие квартиры сейчас.</p>
        </div>
      </details>
      <button type="submit" disabled={!location || loading===key && !!key} className="w-full rounded-xl bg-[#087e75] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">Проверить предпочтения</button>
    </form>}
    {key && loading===key && <p role="status" className="mt-4 text-sm">Проверяем приоритеты и маршруты…</p>}
    {key && error?.key===key && <div role="alert" className="mt-4 text-sm text-[#76562b]">{error.message}<button className="mt-2 block underline" type="button" onClick={() => setAttempt(v => v+1)}>Повторить проверку предпочтений</button></div>}
    {current && !error && <div aria-label="Результат предпочтений" className="mt-4 space-y-4">
      <div>{fit?.availability==='AVAILABLE' ? <><p className="text-sm font-semibold">Infrastructure Fit</p><p className="mt-1 text-2xl font-semibold">{Math.round(fit.score!)} / 100</p><ul className="mt-3 space-y-2 text-xs">{fit.contributions.map(c => <li key={c.component} className="flex min-w-0 justify-between gap-2"><span>{labels[c.component==='stop_availability' ? 'stop' : c.component]}: {c.utility===null ? 'нет данных' : Math.round(c.utility)}</span><span className="text-right text-[#607f82]">{importanceLabels[c.importance!]} · вклад {c.contribution?.toFixed(1)}</span></li>)}</ul></> : <p className="text-sm">{fit?.unavailable_reason==='all_importance_zero' ? 'Все факторы исключены. Оценка не рассчитана.' : fit?.unavailable_reason==='importance_missing' ? 'Укажите важность всех пяти факторов. «Не важно» исключает фактор; «Не указано» не заменяется нулём.' : 'Для важных вам факторов нет подтверждённых данных.'}</p>}</div>
      {current.personal_fit.mobility.destinations.map((d,i) => <div key={i} className="rounded-xl bg-[#f1f8f5] p-3 text-xs"><p className="font-semibold">{d.destination.label || 'Важное место'}</p>{d.route?.availability==='AVAILABLE' ? <><p className="mt-1">{Math.ceil(d.route.duration_seconds!/60)} мин на машине · без текущих пробок</p>{d.within_threshold!==null && <p className="mt-1">{d.within_threshold ? 'Укладывается' : 'Не укладывается'} в ваши {d.destination.max_acceptable_minutes} мин.</p>}</> : <p className="mt-1">{d.availability==='NOT_CALCULATED' ? 'Поездка исключена из проверки.' : d.mode==='public_transport' ? 'Нет подтверждённого источника маршрутов и расписаний общественного транспорта.' : 'Маршрут недоступен. Расчётное время не подставляется.'}</p>}</div>)}
      {current.personal_fit.affordability.availability==='AVAILABLE' ? <div className="text-xs"><p className="font-semibold">Наблюдаемая цена от {Number(current.personal_fit.affordability.observed_price_from).toLocaleString('ru-RU')} ₽</p><p className="mt-1">{current.personal_fit.affordability.within_budget ? 'В пределах бюджета' : 'Выше бюджета'} · разница {Number(current.personal_fit.affordability.budget_delta).toLocaleString('ru-RU')} ₽</p><p className="mt-1 text-[#607f82]">CIAN: стартовая цена, не цена сделки. Актуальность и наличие квартиры нужно проверить.</p></div> : submitted?.profile.purchase_budget!==null && <p className="text-xs text-[#607f82]">Бюджет не проверен: выберите реальный ЖК с известной стартовой ценой.</p>}
    </div>}
  </section>;
}
