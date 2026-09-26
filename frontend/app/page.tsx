import { ArrowRight, Building2, MapPin, Route, Wallet } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

async function backendStatus(): Promise<boolean> {
  try {
    const response = await fetch(`${process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    return response.ok && (await response.json()).database === "ok";
  } catch {
    return false;
  }
}

const features = [
  { icon: MapPin, title: "Районы", text: "Сравните окружение и повседневные маршруты." },
  { icon: Route, title: "Время в пути", text: "Учитывайте места, куда ездите каждую неделю." },
  { icon: Wallet, title: "Финансы", text: "Оцените покупку, аренду и ипотеку в одном сценарии." },
];

export default async function Home() {
  const connected = await backendStatus();
  return (
    <main className="min-h-screen bg-canvas text-navy">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-7 md:px-10">
        <Link href="/" className="flex items-center gap-2 text-2xl font-black tracking-tight" aria-label="МЕСТО — главная">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-turquoise text-white"><MapPin size={22} /></span>
          МЕСТО
        </Link>
        <span className="hidden text-sm font-medium text-slate-500 sm:block">Красноярск · геоаналитика жизни</span>
      </header>

      <section className="mx-auto grid max-w-7xl gap-14 px-6 pb-20 pt-16 md:grid-cols-[1.2fr_0.8fr] md:px-10 md:pt-24">
        <div>
          <p className="mb-5 inline-flex rounded-full bg-teal-50 px-4 py-2 text-sm font-semibold text-teal-700">Новый взгляд на выбор жилья</p>
          <h1 className="max-w-3xl text-5xl font-bold leading-[1.08] tracking-tight md:text-7xl">Найди место, которое сможешь назвать <span className="text-turquoise">домом.</span></h1>
          <p className="mt-7 max-w-2xl text-lg leading-relaxed text-slate-600">Расскажи немного о своей жизни — мы сравним районы, дорогу, инфраструктуру и финансовые сценарии.</p>
          <Button asChild className="mt-9 shadow-lg shadow-slate-300"><a href="#how-it-works">Начать подбор <ArrowRight size={19} /></a></Button>
          <p className="mt-5 text-sm text-slate-500">Персональный подбор появится на следующем этапе.</p>
        </div>

        <div className="relative flex min-h-[360px] items-center justify-center rounded-[2rem] bg-[#e6f1f0] p-6 md:min-h-[470px]">
          <div className="absolute inset-6 rounded-[1.5rem] border border-white/80 bg-[radial-gradient(circle_at_35%_40%,#9bd7d0_0_2%,transparent_2.4%),radial-gradient(circle_at_65%_65%,#9bd7d0_0_2%,transparent_2.4%),linear-gradient(135deg,#d3e8e5_25%,#f2f8f7_25%_50%,#d3e8e5_50%_75%,#f2f8f7_75%)] bg-[length:auto,auto,64px_64px] opacity-70" aria-hidden="true" />
          <div className="relative w-full max-w-sm rounded-card bg-white p-7 shadow-xl shadow-slate-300/50">
            <div className="mb-5 flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-teal-50 text-turquoise"><Building2 size={22} /></span><span className="font-semibold">Твой сценарий жизни</span></div>
            <div className="space-y-4 text-sm text-slate-600">
              <div className="flex justify-between border-b border-slate-100 pb-3"><span>Город</span><strong className="text-navy">Красноярск</strong></div>
              <div className="flex justify-between border-b border-slate-100 pb-3"><span>Районы и дорога</span><strong className="text-navy">Вместе</strong></div>
              <div className="flex justify-between"><span>Финансовый выбор</span><strong className="text-navy">Под контролем</strong></div>
            </div>
          </div>
        </div>
      </section>

      <section id="how-it-works" className="bg-white py-20">
        <div className="mx-auto max-w-7xl px-6 md:px-10">
          <p className="font-semibold text-turquoise">Как это работает</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-bold tracking-tight md:text-5xl">Выбор дома начинается с твоей жизни</h2>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {features.map(({ icon: Icon, title, text }) => (
              <article key={title} className="rounded-card border border-slate-100 bg-canvas p-7">
                <span className="mb-6 grid h-12 w-12 place-items-center rounded-2xl bg-teal-50 text-turquoise"><Icon size={23} /></span>
                <h3 className="text-xl font-bold">{title}</h3>
                <p className="mt-2 leading-relaxed text-slate-600">{text}</p>
              </article>
            ))}
          </div>
          <p className="mt-8 text-sm text-slate-500" role="status">Состояние платформы: {connected ? "API и база данных доступны" : "API или база данных пока недоступны"}</p>
        </div>
      </section>
    </main>
  );
}
