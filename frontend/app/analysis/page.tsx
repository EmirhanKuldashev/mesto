"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Check, LoaderCircle } from "lucide-react";
import { Brand } from "@/components/concept-ui";
import { useAnalytics } from "@/lib/analytics-store";
import { useOnboarding } from "@/lib/onboarding-store";
import { useOnboardingReady } from "@/lib/use-onboarding-ready";

const stages = [
  { key: "profile", label: "Анализируем ваши предпочтения" },
  { key: "districts", label: "Изучаем районы" },
  { key: "scoring", label: "Оцениваем пять показателей территории" },
  { key: "future_growth", label: "Проверяем развитие территории" },
  { key: "recommendations", label: "Формируем рекомендации" },
] as const;

export default function AnalysisPage() {
  const router = useRouter();
  const ready = useOnboardingReady();
  const profileId = useOnboarding((state) => state.profileId);
  const { stage, status, load } = useAnalytics();

  useEffect(() => {
    if (!ready) return;
    void load(profileId).then(() => router.replace("/results"));
  }, [ready, load, profileId, router]);
  const current = stages.findIndex((item) => item.key === stage);

  return <main className="page-shell mesh-background min-h-screen"><header className="content-shell flex h-20 items-center"><Brand /></header>
    <section className="content-shell flex min-h-[calc(100vh-80px)] flex-col items-center justify-center text-center">
      <h1 className="section-title">Создаём ваш персональный анализ</h1>
      <p role="status" className="mt-5 max-w-xl text-[#b5d2cf]">{!ready ? "Восстанавливаем сохранённый сценарий…" :
        !profileId ? "Для персонального анализа сначала сохраните анкету." :
        status === "loading" ? "Получаем данные и рассчитываем результат через API." : "Завершаем анализ…"}</p>
      <div className="mt-8 w-full max-w-lg space-y-3 text-left">{stages.map((item, index) =>
        <div key={item.key} className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[.06] px-5 py-4 text-sm">
          <span className="text-[#9ce9d2]">{index < current ? <Check size={18} /> : index === current && ready && profileId ?
            <LoaderCircle size={18} className="animate-spin" /> : <span className="inline-block h-4 w-4 rounded-full border border-white/30" />}</span>{item.label}
        </div>)}
      </div>
      <Link href="/onboarding" className="mt-8 text-sm font-semibold text-[#9ce9d2] underline underline-offset-4">Изменить сценарий</Link>
    </section>
  </main>;
}
