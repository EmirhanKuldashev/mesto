export type DistrictRecommendation = {
  district_id: number;
  district_name: string;
  profile_id: string;
  match_score: number;
  district_score: number | null;
  future_score: number | null;
  rank: number;
  reasons: string[];
  warnings: string[];
  created_at: string;
};

export type RecommendationResponse = { recommendations: DistrictRecommendation[] };
