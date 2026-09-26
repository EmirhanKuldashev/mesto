"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Check, LoaderCircle } from "lucide-react";
import { Brand } from "@/components/concept-ui";
import { useAnalytics } from "@/lib/analytics-store";
import { useOnboarding } from "@/lib/onboarding-store";

const stages = [
  { key: "profile", label: "Анализируем профиль" },
  { key: "districts", label: "Получаем районы" },
  { key: "scoring", label: "Считаем совместимость и проверяем развитие территории" },
] as const;

export default function AnalysisPage() {
  const router = useRouter();
  const profileId = useOnboarding((state) => state.profileId);
  const { stage, status, load } = useAnalytics();

  useEffect(() => { void load(profileId).then(() => router.replace("/results")); }, [load, profileId, router]);
  const current = stages.findIndex((item) => item.key === stage);

  return <main className="page-shell mesh-background min-h-screen"><header className="content-shell flex h-20 items-center"><Brand /></header>
    <section className="content-shell flex min-h-[calc(100vh-80px)] flex-col items-center justify-center text-center"><h1 className="section-title">Готовим ваш MESTO Score</h1>
      <p role="status" className="mt-5 max-w-xl text-[#b5d2cf]">{status === "demo" ? "Открываем демонстрационный пример…" : "Получаем данные для персональной оценки районов."}</p>
      <div className="mt-8 w-full max-w-lg space-y-3 text-left">{stages.map((item, index) => <div key={item.key} className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[.06] px-5 py-4 text-sm"><span className="text-[#9ce9d2]">{index < current ? <Check size={18} /> : index === current ? <LoaderCircle size={18} className="animate-spin" /> : <span className="inline-block h-4 w-4 rounded-full border border-white/30" />}</span>{item.label}</div>)}</div>
    </section>
  </main>;
}
