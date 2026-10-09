"use client";
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useOnboarding } from '@/lib/onboarding-store';
import { matchProfile } from '@/lib/match-profile';
import { recommendationsV2 } from '@/lib/api/recommendations-v2';
import type { LocalLocation } from '@/types/local';
import type { MatchCandidate, MatchResponse } from '@/types/recommendations-v2';
import { MatchPreferences } from './match-preferences';

const domainNames:Record<string,string>={infrastructure:'Инфраструктура',mobility:'Поездки',affordability:'Финансы'};
const infraNames:Record<string,string>={stop_availability:'Остановки',school:'Школы',kindergarten:'Детские сады',healthcare:'Медицина',parks:'Парки'};
const value=(v:number|null)=>v===null?'не рассчитано':`${v.toFixed(1)}/100`;
const reasons:Record<string,string>={domain_weights_missing:'Укажите важность каждой области, включая исключённые.',all_domains_excluded:'Все области исключены: общий балл не имеет смысла.',active_domain_unavailable:'Нет оценки хотя бы одной включённой области.',rent_and_compare_not_supported:'Для аренды и сравнения с арендой полный Match пока недоступен.',importance_missing:'Уточните пять приоритетов инфраструктуры.',all_importance_zero:'Все инфраструктурные компоненты исключены.',positive_weight_component_unavailable:'Нет данных включённого инфраструктурного компонента.',frequency_weighting_not_confirmed:'Подтвердите учёт частоты поездок.',trip_preferences_missing:'Уточните важность и частоту включённых поездок.',no_included_soft_trips:'Нет поездок, включённых в мягкую оценку.',soft_time_anchors_missing:'Укажите комфортное время и мягкий предел.',route_missing:'Маршрут не рассчитан: проверьте транспорт и координаты.',public_transport_source_unavailable:'Нет проверенного источника общественного транспорта.',price_or_comfortable_anchor_missing:'Для финансового балла нужны известная цена и комфортный ценовой ориентир.'};
const reasonText=(reason:string|null)=>reason ? reasons[reason] ?? 'Необходимые данные недоступны; оценка не подменяется нулём.' : null;
function Candidate({candidate:c}:{candidate:MatchCandidate}){
  return <div className="min-w-0 space-y-3">
    <p className="font-semibold">{c.district_name ?? 'Принадлежность району не подтверждена'}</p>
    <p className="text-xl font-semibold">{c.score===null?'Общий Match не рассчитан':`Match ${value(c.score)}`}</p>
    {c.score===null && <p className="text-sm">Уточните включённые области и настройки. Отсутствующие данные не заменяются нулём и не исключаются из суммы.</p>}
    {c.score_reason && <p className="text-sm">{reasonText(c.score_reason)}</p>}
    <p className="text-xs">MESTO Local: {value(c.objective_local?.score ?? null)} · MESTO Score района: {value(c.objective_district?.score ?? null)}. Объективные оценки не прибавляются к Match.</p>
    <dl className="space-y-2 text-sm">{Object.entries(c.domains).map(([k,d])=><div key={k}><dt className="font-medium">{domainNames[k]}</dt><dd>{d.weight===0?'Исключено вами из общего балла.':`Полезность ${value(d.score)}`} · вес {d.weight===null?'не задан':`${(d.weight*100).toFixed(1)}%`} · вклад {d.contribution===null?'не рассчитан':d.contribution.toFixed(1)}{d.weight!==0 && d.reason && <p>{reasonText(d.reason)}</p>}</dd></div>)}</dl>
    <p className="text-sm">Наблюдаемая стартовая цена: {c.price_from===null?'неизвестна':`${Number(c.price_from).toLocaleString('ru-RU')} ₽`}. Наличие квартиры не подтверждено.</p>
    <h4 className="font-semibold">Обязательные требования</h4>
    {c.constraints.length===0?<p className="text-sm">Обязательные требования не заданы.</p>:<ul className="space-y-2 text-sm">{c.constraints.map(check=><li key={check.key}>{check.key==='budget'?'Бюджет':check.key==='housing_goal'?'Сценарий жилья':check.key.startsWith('distance:')?`Расстояние: ${infraNames[check.key.slice(9)]}`:`Поездка ${Number(check.key.slice(5))+1}`}: <strong>{check.status==='PASS'?'выполнено':check.status==='FAIL'?'нарушено':'не проверено'}</strong>. Факт: {check.actual ?? 'нет данных'}; максимум: {check.limit ?? 'не задан'}.</li>)}</ul>}
    <details><summary className="cursor-pointer font-semibold">Почему получилась эта оценка</summary>
      <ul className="mt-3 space-y-2 text-sm">{Object.entries(c.objective_local?.components ?? {}).map(([k,d])=><li key={k}>{infraNames[k]}: {d.distance_m===null?'расстояние неизвестно':`${Math.round(d.distance_m)} м по пространственной методике`} · {value(d.score)}.</li>)}</ul>
      {Array.isArray(c.domains.infrastructure.evidence.contributions) && <ul className="mt-3 space-y-2 text-sm">{c.domains.infrastructure.evidence.contributions.map((item,index)=>{const e=item as {component:string;importance:number|null;normalized_weight:number|null;contribution:number|null};return <li key={index}>{infraNames[e.component]}: важность {e.importance ?? 'не задана'}, вес внутри Infrastructure Fit {e.normalized_weight===null?'не задан':`${(e.normalized_weight*100).toFixed(1)}%`}, вклад {e.contribution===null?'не рассчитан':e.contribution.toFixed(1)}.</li>;})}</ul>}
      {Array.isArray(c.domains.mobility.evidence.trips) && c.domains.mobility.evidence.trips.map((entry,index)=>{const e=entry as {trip:{label:string;comfortable_minutes:number|null;soft_limit_minutes:number|null;importance:number|null;visits_per_week:number|null};minutes:number|null;utility:number|null};return <p key={index} className="mt-3 text-sm">{e.trip.label}: {e.minutes===null?'маршрут недоступен':`${e.minutes.toFixed(1)} мин без текущих пробок`}; комфорт {e.trip.comfortable_minutes ?? 'не задан'}, мягкий предел {e.trip.soft_limit_minutes ?? 'не задан'} мин; полезность {value(e.utility)}; важность {e.trip.importance ?? 'не задана'} × частота {e.trip.visits_per_week ?? 'не задана'}.</p>;})}
      <p className="mt-3 text-sm">Комфортная цена: {String(c.domains.affordability.evidence.comfortable_price ?? 'не задана')}; максимальный бюджет: {String(c.domains.affordability.evidence.maximum_budget ?? 'не задан')} ₽.</p>
      <p className="mt-3 text-xs">Близость не означает качество или вместимость услуг. Баллы не являются вероятностью удовлетворённости. Координата ЖК — ориентир источника, не проверенный вход.</p>
      <p className="mt-2 text-xs">Источник: {String(c.source.source_id ?? 'точка пользователя')} · версия {String(c.source.source_version ?? 'не указана')} · загрузка {String(c.source.fetched_at ?? 'не указана')}.</p>
    </details>
    {c.district_id!==null && <Link className="inline-block text-sm underline" href={`/district?districtId=${c.district_id}`}>Посмотреть район</Link>}
  </div>;
}
export function MatchRecommendations({point,onActiveChange}:{point?:LocalLocation|null;onActiveChange?:(active:boolean)=>void}){
  const draft=useOnboarding(s=>s.draft);
  const [active,setActive]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const [result,setResult]=useState<{key:string;data:MatchResponse}|null>(null),[compare,setCompare]=useState<string[]>([]);
  const controller=useRef<AbortController|null>(null),generation=useRef(0);
  const profile=useMemo(()=>matchProfile(draft),[draft]);
  const key=JSON.stringify({profile,point});
  useEffect(()=>{generation.current++;controller.current?.abort();setBusy(false);setError(null);setCompare([]);return ()=>controller.current?.abort();},[key]);
  const current=result?.key===key?result.data:null;
  async function calculate(){
    controller.current?.abort();const abort=new AbortController();controller.current=abort;const id=++generation.current;
    setBusy(true);setError(null);const timer=setTimeout(()=>abort.abort(),35000);
    try{const data=await recommendationsV2(profile,abort.signal,point ?? undefined);if(generation.current===id)setResult({key,data});}
    catch(e){if(generation.current===id)setError(abort.signal.aborted?'Расчёт прерван по времени. Повторите попытку.':e instanceof Error?e.message:'Не удалось получить Match');}
    finally{clearTimeout(timer);if(generation.current===id)setBusy(false);}
  }
  const candidateKey=(c:MatchCandidate)=>c.id===null?'point':String(c.id);
  return <section aria-label="Match V2 рекомендации" className="min-w-0 space-y-5 rounded-[26px] border border-[#dbe8e4] bg-white p-5 text-[#153c44]">
    <h2 className="text-2xl font-semibold">Match V2 · персональный выбор места</h2>
    <p className="text-sm">Покупка и автомобильные маршруты. Оцениваем наблюдаемые ЖК, а не весь рынок квартир. Итог отражает ваши явно выбранные приоритеты.</p>
    <label className="flex gap-2 text-sm"><input aria-label="Включить Match V2" type="checkbox" checked={active} onChange={e=>{setActive(e.target.checked);onActiveChange?.(e.target.checked);if(!e.target.checked){controller.current?.abort();generation.current++;setBusy(false);}}}/>Включить новую выдачу Match V2</label>
    {active && <><details open={!draft.match_v2 || Object.values(draft.match_v2.domains).some(v=>v===null)}><summary className="cursor-pointer font-semibold">Уточнить общую анкету</summary><MatchPreferences/></details>
      {point===null && <p>Выберите точку на карте для оценки конкретного места.</p>}
      <button className="primary-button" disabled={busy || point===null} type="button" onClick={()=>void calculate()}>Рассчитать Match V2</button>
      {busy && <p role="status">Проверяем выбранные области, бюджет и маршруты…</p>}
      {error && <p role="alert">{error} <button type="button" className="underline" onClick={()=>void calculate()}>Повторить</button></p>}
      {current && <><p>Выборка: {current.sample.count} {point?'точка':'наблюдаемых ЖК'}. Нет подтверждённого района: {current.sample.unassigned_count}. Не полный рынок жилья.</p>
        {!point && <details><summary className="cursor-pointer font-semibold">Наблюдаемые варианты по районам</summary><div className="mt-3 space-y-3">{current.districts.map(d=><div key={d.district_id}><strong>{d.district_name}</strong>: наблюдается {d.observed_count}, инфраструктура оценена для {d.evaluated_count}, проверено {d.verified_count}, непроверено {d.unknown_count}, не подходит {d.failed_count}. Лучший оценённый вариант: {value(d.best_observed_match)}.</div>)}</div><p className="mt-3 text-xs">Это лучший найденный вариант, а не совместимость всего района. Размеры выборок различаются; максимум может быть выше там, где наблюдений больше.</p></details>}
        {compare.length>0 && <section id="match-v2-comparison" aria-label="Сравнение Match V2"><h3 className="mb-3 text-xl font-semibold">Сравнение на одинаковых предпочтениях</h3><div className="grid min-w-0 gap-4 md:grid-cols-2">{current.candidates.filter(c=>compare.includes(candidateKey(c))).map(c=><div key={candidateKey(c)} className="min-w-0 rounded-xl border p-4"><h4 className="mb-3 font-semibold">{c.name}</h4><Candidate candidate={c}/></div>)}</div></section>}
        {(['verified','unknown','failed'] as const).map(bucket=><section key={bucket} aria-label={{verified:'Проверенные варианты',unknown:'Непроверенные варианты',failed:'Не подходят требованиям'}[bucket]} className="space-y-4"><h3 className="text-xl font-semibold">{{verified:'Проверенные варианты',unknown:'Непроверенные варианты',failed:'Не подходят требованиям'}[bucket]} ({current.candidates.filter(c=>c.bucket===bucket).length})</h3>{current.candidates.filter(c=>c.bucket===bucket).map(c=><article key={candidateKey(c)} className="rounded-xl border p-4"><h4 className="mb-3 text-lg font-semibold">{c.name}</h4><label className="mb-3 flex gap-2 text-sm"><input aria-label={`Сравнить: ${c.name}`} type="checkbox" checked={compare.includes(candidateKey(c))} disabled={!compare.includes(candidateKey(c)) && compare.length>=2} onChange={e=>setCompare(v=>e.target.checked?[...v,candidateKey(c)]:v.filter(k=>k!==candidateKey(c)))}/>Сравнить, до двух вариантов</label>{compare.includes(candidateKey(c)) && <a className="mb-3 inline-block text-sm underline" href="#match-v2-comparison">Посмотреть сравнение ({compare.length})</a>}<Candidate candidate={c}/></article>)}</section>)}
        {current.candidates.length===0 && <p role="status">В наблюдаемой выборке нет кандидатов. Подходящие квартиры не выдумываются.</p>}
      </>}
    </>}
  </section>;
}
