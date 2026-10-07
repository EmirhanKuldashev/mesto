export const localKeys = ["stop_availability", "school", "kindergarten", "healthcare", "parks"] as const;
export type LocalKey = typeof localKeys[number];
export type LocalLocation = { latitude: number; longitude: number };
export type LocalComponent = {
  key: LocalKey; score: number | null; distance_m: number | null; available: boolean;
  normalization_version: string; evidence_version: string; eligibility_version: string;
  reference_id: string; reference_checksum: string; distance_method: string;
  unavailable_reason: string | null; inside_geometry: boolean | null;
  nearest: { source_id: "osm"; osm_type: "node" | "way" | "relation"; osm_id: number;
    name: string | null; category: string; distance_m: number; coordinate_representation: string | null } | null;
  limitations: string[]; provenance: Record<string, unknown>;
};
export type LocalResult = {
  version: "local-objective-v1"; availability: "AVAILABLE" | "UNAVAILABLE";
  score: number | null; location: LocalLocation; components: Record<LocalKey, LocalComponent>;
  weights: Record<LocalKey, number>; provenance: Record<string, unknown>;
  limitations: string[]; unavailable_reason: string | null;
};
