"use client";

import { create } from "zustand";
import { AnalyticsApiError, calculateScore, getDistrictIds } from "@/lib/api/analytics";
import { getRecommendations } from "@/lib/api/recommendations";
import { demoScores } from "@/lib/demo-analytics";
import type { DistrictScoreResponse } from "@/types/analytics";
import type { DistrictRecommendation } from "@/types/recommendations";

type Status = "idle" | "loading" | "ready" | "empty" | "demo";
type Stage = "profile" | "districts" | "scoring" | "future_growth" | "recommendations";
type State = {
  status: Status;
  stage: Stage;
  profileId: string | null;
  scores: DistrictScoreResponse[];
  recommendations: DistrictRecommendation[];
  recommendationError: string | null;
  error: string | null;
  load: (profileId: string | null, force?: boolean) => Promise<void>;
  clear: () => void;
};

let pending: Promise<void> | null = null;
let generation = 0;

export const useAnalytics = create<State>((set, get) => ({
  status: "idle", stage: "profile", profileId: null, scores: [], recommendations: [],
  recommendationError: null, error: null,
  clear: () => {
    generation++; pending = null;
    set({ status: "idle", stage: "profile", profileId: null, scores: [], recommendations: [],
      recommendationError: null, error: null });
  },
  load: (profileId, force = false) => {
    if (pending && get().profileId === profileId) return pending;
    if (!force && get().profileId === profileId && ["ready", "empty", "demo"].includes(get().status))
      return Promise.resolve();
    if (!profileId) {
      generation++;
      const error = sessionStorage.getItem("mesto-save-status");
      sessionStorage.removeItem("mesto-save-status");
      set({ status: "demo", stage: "profile", profileId: null, scores: demoScores,
        recommendations: [], recommendationError: null, error });
      return Promise.resolve();
    }
    const requestGeneration = ++generation;
    set({ status: "loading", stage: "profile", profileId, scores: [], recommendations: [],
      recommendationError: null, error: null });
    pending = (async () => {
      try {
        set({ stage: "districts" });
        const districtIds = await getDistrictIds();
        if (requestGeneration !== generation) return;
        if (districtIds.length === 0) {
          set({ status: "empty", scores: [], recommendations: [] });
          return;
        }
        set({ stage: "scoring" });
        const scores = await calculateScore(profileId, districtIds);
        if (requestGeneration !== generation) return;
        set({ stage: "future_growth", scores });
        if (scores.length === 0) {
          set({ status: "empty" });
          return;
        }
        set({ stage: "recommendations" });
        try {
          const recommendations = (await getRecommendations(profileId)).recommendations;
          if (requestGeneration === generation) set({ status: "ready", recommendations, recommendationError: null });
        } catch (reason) {
          if (requestGeneration === generation) set({ status: "ready", recommendations: [],
            recommendationError: reason instanceof Error ? reason.message : "Не удалось получить рекомендации" });
        }
      } catch (reason) {
        if (requestGeneration === generation) set({ status: "demo", scores: demoScores, recommendations: [],
          error: reason instanceof AnalyticsApiError ? reason.message : "Не удалось получить анализ. Попробуйте позже." });
      } finally { if (requestGeneration === generation) pending = null; }
    })();
    return pending;
  },
}));
