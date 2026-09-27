"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Construction, GraduationCap, Route } from "lucide-react";
import type { ExternalSignal, SignalsResponse } from "@/types/intelligence";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const names: Record<ExternalSignal["category"], string> = {
  education: "Образование", transport: "Транспорт", healthcare: "Медицина",
  environment: "Экология", commercial: "Коммерция", housing: "Жильё",
};

export function SignalPanel({ districtId }: { districtId: number }) {
  const [signals, setSignals] = useState<ExternalSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setSignals([]); setError(null);
    fetch(`${API_URL}/api/intelligence/signals/${districtId}`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload: SignalsResponse = await response.json();
        if (!Array.isArray(payload?.signals)) throw new Error("Некорректный ответ API");
        return payload.signals;
      })
      .then((items) => { if (!controller.signal.aborted) setSignals(items.filter((item) => !item.is_demo)); })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Ошибка загрузки");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [districtId]);

  return <section className="rounded-[28px] border border-[#dbe9e4] bg-white p-6 text-[#153c44] sm:p-8">
    <h2 className="text-xl font-semibold">Сигналы развития района</h2>
    <p className="mt-2 text-sm text-[#647f80]">Записи из существующего API. Влияние учитывает указанную уверенность.</p>
    {loading && <p role="status" className="mt-5 text-sm">Загружаем сигналы…</p>}
    {error && <p role="alert" className="mt-5 flex items-center gap-2 text-sm text-[#a15c49]"><AlertTriangle size={16} />Не удалось получить сигналы: {error}</p>}
    {!loading && !error && signals.length === 0 && <p className="mt-5 text-sm text-[#647f80]">Подтверждённых сигналов для района пока нет.</p>}
    {!loading && !error && signals.length > 0 && <div className="mt-5 grid gap-3 md:grid-cols-2">
      {signals.map((signal) => {
        const Icon = signal.category === "education" ? GraduationCap : signal.category === "transport" ? Route : Construction;
        return <article key={signal.id} className="rounded-[20px] border border-[#dcebe6] bg-[#f4faf7] p-5">
          <div className="flex items-start gap-3"><Icon size={20} className="mt-0.5 shrink-0 text-[#168e79]" /><div><h3 className="font-semibold">{signal.title}</h3><p className="mt-1 text-xs text-[#647f80]">{names[signal.category]}</p></div></div>
          {signal.description && <p className="mt-3 text-sm text-[#547477]">{signal.description}</p>}
          <p className="mt-3 text-sm">Влияние: <strong>{signal.impact}</strong> · Учтено: <strong>{signal.future_growth_impact > 0 ? "+" : ""}{signal.future_growth_impact}</strong> · Уверенность: {Math.round(signal.confidence * 100)}%</p>
        </article>;
      })}
    </div>}
  </section>;
}
