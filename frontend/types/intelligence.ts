export type ExternalSignal = {
  id: number;
  district_id: number;
  source_type: "news" | "tender" | "construction" | "government_plan" | "other";
  title: string;
  description: string | null;
  category: "education" | "transport" | "healthcare" | "environment" | "commercial" | "housing";
  impact_direction: "positive" | "negative" | "neutral";
  impact_value: number;
  impact: string;
  future_growth_impact: number;
  confidence: number;
  event_date: string | null;
  is_demo: boolean;
  created_at: string;
};

export type SignalsResponse = { signals: ExternalSignal[] };

export type ExternalSignalImpact = Pick<ExternalSignal,
  "source_type" | "title" | "category" | "future_growth_impact" | "confidence" | "is_demo"> & {
    signal_id: number;
  };
