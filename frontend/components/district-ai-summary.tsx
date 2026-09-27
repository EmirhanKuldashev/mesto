"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { useOnboarding } from "@/lib/onboarding-store";

type Result = { key: string; summary?: string; error?: string };

export function DistrictAiSummary({ districtId }: { districtId: number }) {
  const profileId = useOnboarding((state) => state.profileId);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const key = `${profileId}:${districtId}:${attempt}`;

  useEffect(() => {
    if (!profileId) return;
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => {
      if (active) {
        setResult({ key, error: "Генерация заняла слишком много времени. Попробуйте ещё раз." });
        controller.abort();
      }
    }, 65000);
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    void fetch(`${base}/api/ai/district-summary`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId, district_id: districtId }),
      signal: controller.signal, cache: "no-store",
    }).then(async (response) => {
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "ИИ-сводка временно недоступна.");
      if (data.district_id !== districtId || typeof data.summary !== "string" || !data.summary.trim())
        throw new Error("Не удалось получить сводку. Попробуйте ещё раз.");
      if (active) setResult({ key, summary: data.summary });
    }).catch((reason: unknown) => {
      if (active && !controller.signal.aborted)
        setResult({ key, error: reason instanceof Error ? reason.message : "ИИ-сводка временно недоступна." });
    }).finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [profileId, districtId, key]);

  if (!profileId) return null;
  const current = result?.key === key ? result : null;
  return <section aria-label="Персональная ИИ-сводка" className="rounded-[28px] border border-[#b8ded1] bg-[#eaf7f0] p-6 text-[#153c44] sm:p-8">
    <div className="flex items-center gap-2"><Sparkles size={21} className="text-[#168e79]" /><h2 className="text-xl font-semibold">Насколько район подходит вам</h2><span className="ml-auto rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#138d7b]">ИИ-сводка</span></div>
    <div aria-live="polite" aria-busy={!current} className="mt-4 text-sm leading-relaxed sm:text-base">
      {!current && <p role="status" className="animate-pulse text-[#54787a]">Сопоставляем район с вашими ответами…</p>}
      {current?.summary && <p className="whitespace-pre-line">{current.summary}</p>}
      {current?.error && <div><p role="alert" className="text-[#76562b]">{current.error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-3 font-semibold text-[#138d7b] underline">Повторить</button></div>}
    </div>
    <p className="mt-4 text-xs text-[#69857d]">На основе вашей анкеты и доступных данных района. Важные детали о жилье стоит проверить перед выбором.</p>
  </section>;
}
