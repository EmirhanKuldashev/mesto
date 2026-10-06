import type { DistrictScoreResponse } from "@/types/analytics";
import { displayScore, isDisplayScore, objectiveComponents, objectiveValue, unavailableExplanation } from "@/lib/objective-presentation";

export function ObjectiveScore({ score }: { score: DistrictScoreResponse }) {
  const objective = score.objective;
  const value = objectiveValue(score);
  return <section aria-label="Объективная оценка территории" className="min-w-0 space-y-4">
    <div className="min-w-0 rounded-[30px] border border-white/15 bg-gradient-to-br from-[#185652] via-[#103c47] to-[#0b2939] p-6 text-white shadow-[0_25px_80px_rgba(4,24,35,.25)] sm:p-9">
      <h2 className="text-sm font-bold tracking-[.15em] text-[#a4e9d3]">MESTO Score</h2>
      <p className="mt-2 text-lg font-medium">Объективная оценка территории</p>
      <p className="mt-2 break-words text-sm text-[#b9d4d0]">{score.district.name}</p>
      {value !== null ? <div aria-label={`MESTO Score: ${displayScore(value)} из 100`} className="mt-6 flex items-end gap-2">
        <span className="text-[clamp(4.5rem,11vw,8rem)] font-semibold leading-none tracking-[-.09em]">{displayScore(value)}</span>
        <span className="pb-2 text-2xl text-[#a7ceca]">/100</span>
      </div> : <div role="status" className="mt-6">
        <p className="text-xl font-semibold">Объективная оценка временно недоступна</p>
        <p className="mt-3 text-sm leading-relaxed text-[#b9d4d0]">{unavailableExplanation(objective?.unavailable_reason)}</p>
      </div>}
      <p className="mt-5 text-sm leading-relaxed text-[#b9d4d0]">MESTO Score формируется из пяти объективных показателей территории с равными весами по 20%.</p>
    </div>
    <div className="rounded-[28px] border border-[#dbe9e4] bg-white p-5 text-[#153c44] sm:p-8">
      <h3 className="text-xl font-semibold">Из чего состоит MESTO Score</h3>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{objectiveComponents.map(({ key, label, description }) => {
        const component = objective?.components?.[key];
        const available = objective?.calculation_version === "objective-mesto-v2" &&
          isDisplayScore(component?.score) && !component?.unavailable_reason;
        const componentValue = available ? component!.score! : null;
        const weight = objective?.weights?.[key];
        return <article key={key} aria-label={label} className="min-w-0 rounded-[20px] bg-[#f1f8f5] p-5">
          <div className="flex items-start justify-between gap-3"><h4 className="font-semibold">{label}</h4>
            <span className="shrink-0 text-xl font-bold text-[#168e79]" aria-label={`${label}: ${componentValue === null ? "нет данных" : `${displayScore(componentValue)} из 100`}`}>{displayScore(componentValue)}</span></div>
          {componentValue !== null && <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={componentValue}
            aria-valuetext={`${displayScore(componentValue)} из 100`} className="mt-4 h-2 overflow-hidden rounded-full bg-[#dcebe6]">
            <div style={{ width: `${componentValue}%` }} className="h-full rounded-full bg-[#2fb593]" />
          </div>}
          <p className="mt-3 text-xs leading-relaxed text-[#647f80]">{description}</p>
          <p className="mt-3 text-xs font-semibold text-[#547477]">Вес: {typeof weight === "number" && Number.isFinite(weight) ? `${Math.round(weight * 100)}%` : "не указан"}{componentValue === null && " · Нет данных"}</p>
        </article>;
      })}</div>
      <details className="mt-6 border-t border-[#dbe9e4] pt-5 text-sm leading-relaxed text-[#547477]">
        <summary className="cursor-pointer font-semibold text-[#153c44]">Как считается MESTO Score</summary>
        <div className="mt-3 space-y-3">
          <p>Итоговый балл приходит из аналитического ядра: каждый из пяти компонентов вносит 20%. На экране баллы округлены до целых, поэтому среднее видимых значений может немного отличаться от итогового балла.</p>
          <p>Оценка относительна к зафиксированным данным Красноярска. Она описывает территорию, а не соответствие вашей анкете — для этого есть Match Score. Рынок жилья и бюджет оцениваются отдельно, будущие изменения — в Growth.</p>
          <p>Показатели отражают пространственную близость, а не качество, вместимость или доступность услуг. Близость к остановкам не учитывает маршруты, частоту движения и время в пути. Расстояния не означают время пешком.</p>
          <p>Наличие всех компонентов не означает полноту или актуальность информации о районе. Покрытие реального мира и свежесть данных не подтверждены.</p>
          {typeof objective?.coverage === "number" && Number.isFinite(objective.coverage) &&
            <p>Покрытие компонентов: {Math.round(objective.coverage * 100)}%. Это доля рассчитанных обязательных компонентов, а не полнота данных о районе.</p>}
        </div>
      </details>
    </div>
  </section>;
}
