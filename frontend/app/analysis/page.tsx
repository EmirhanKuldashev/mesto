"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "@/components/concept-ui";

export default function AnalysisPage() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  useEffect(() => {
    const status = sessionStorage.getItem("mesto-save-status") ?? "";
    sessionStorage.removeItem("mesto-save-status");
    setMessage(status);
    if (!status) router.replace("/results");
  }, [router]);

  return <main className="page-shell mesh-background min-h-screen"><header className="content-shell flex h-20 items-center"><Brand /></header>
    <section className="content-shell flex min-h-[calc(100vh-80px)] flex-col items-center justify-center text-center"><h1 className="section-title">Объявления ЦИАН</h1>
      {message ? <><p role="status" className="mt-5 max-w-xl text-[#f3c7ac]">{message}</p><Link href="/results" className="primary-button mt-8">Посмотреть объявления</Link></> : <p role="status" className="mt-5 text-[#a5bdc0]">Открываем загруженные объявления…</p>}
    </section>
  </main>;
}
