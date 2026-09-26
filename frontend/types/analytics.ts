export type CategoryScores = {
  lifestyle: number | null;
  infrastructure: number | null;
  transport: number | null;
  future_growth: number | null;
  market: number | null;
};

export type FutureFactor = {
  object_id: number;
  name: string;
  type: string;
  year: number | null;
  status: string;
  impact: Record<string, number>;
  reason: string;
  distance_km: number | null;
  confidence: number;
  is_synthetic: boolean;
};

export type DistrictScoreResponse = {
  id: number;
  district: { id: number; name: string; slug: string | null };
  score: number | null;
  current_score: number | null;
  future_score: number | null;
  future_growth_score: number | null;
  future_factors: FutureFactor[];
  future_impacts: Record<string, number>;
  categories: CategoryScores;
  confidence: number;
  reasons: string[];
  warnings: string[];
  is_synthetic: boolean;
  calculation_version: string;
  created_at: string;
};
