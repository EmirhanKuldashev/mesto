export type Coordinate = { latitude: number; longitude: number };
export type TravelMode = "car" | "public_transport";
export type DestinationKind = "work" | "university" | "school" | "relatives" | "other";
export type PersonalDestination = Coordinate & { label: string; kind: DestinationKind };
export type MobilityRequest = { origin: Coordinate; destination: PersonalDestination; mode: TravelMode };
export type MobilityResult = MobilityRequest & {
  version: "mobility-v1"; availability: "AVAILABLE" | "UNAVAILABLE";
  duration_seconds: number | null; distance_meters: number | null; departure_time: null;
  traffic: "not_included" | "not_available"; unavailable_reason: string | null;
  provider: string | null; provider_version: string | null; data_timestamp: string | null;
  dataset_id: string | null; dataset_sha256: string | null;
  limitations: string[];
  geometry: { type: "LineString"; coordinates: [number, number][] } | null;
  origin_snap: { location: Coordinate; distance_meters: number } | null;
  destination_snap: { location: Coordinate; distance_meters: number } | null;
};
