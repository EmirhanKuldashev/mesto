"use client";

import { useEffect, useState } from "react";
import { useOnboarding } from "@/lib/onboarding-store";

export function useOnboardingReady() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (useOnboarding.persist.hasHydrated()) setReady(true);
    return useOnboarding.persist.onFinishHydration(() => setReady(true));
  }, []);
  return ready;
}
