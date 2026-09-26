"use client";

import { create } from "zustand";
import { AnalyticsApiError, calculateScore, getDistrictIds } from "@/lib/api/analytics";
import { demoScores } from "@/lib/demo-analytics";
import type { DistrictScoreResponse } from "@/types/analytics";

type Status = "idle" | "loading" | "ready" | "empty" | "demo";
type Stage = "profile" | "districts" | "scoring";
type State = {
  status: Status;
  stage: Stage;
  profileId: string | null;
  scores: DistrictScoreResponse[];
  error: string | null;
  load: (profileId: string | null, force?: boolean) => Promise<void>;
  clear: () => void;
};

let pending: Promise<void> | null = null;
let generation = 0;

export const useAnalytics = create<State>((set, get) => ({
  status: "idle", stage: "profile", profileId: null, scores: [], error: null,
  clear: () => { generation++; pending = null; set({ status: "idle", stage: "profile", profileId: null, scores: [], error: null }); },
  load: (profileId, force = false) => {
    if (pending && get().profileId === profileId) return pending;
    if (!force && get().profileId === profileId && ["ready", "empty", "demo"].includes(get().status))
      return Promise.resolve();
    if (!profileId) {
      generation++;
      const error = sessionStorage.getItem("mesto-save-status");
      sessionStorage.removeItem("mesto-save-status");
      set({ status: "demo", stage: "profile", profileId: null, scores: demoScores, error });
      return Promise.resolve();
    }
    const requestGeneration = ++generation;
    set({ status: "loading", stage: "profile", profileId, scores: [], error: null });
    pending = (async () => {
      try {
        const districtIds = await getDistrictIds(() => set({ stage: "districts" }));
        const scores = await calculateScore(profileId, districtIds, () => set({ stage: "scoring" }));
        if (requestGeneration === generation) set({ status: scores.length ? "ready" : "empty", scores, error: null });
      } catch (reason) {
        if (requestGeneration === generation) set({ status: "demo", scores: demoScores,
          error: reason instanceof AnalyticsApiError ? reason.message : "Не удалось получить анализ. Попробуйте позже." });
      } finally { if (requestGeneration === generation) pending = null; }
    })();
    return pending;
  },
}));
