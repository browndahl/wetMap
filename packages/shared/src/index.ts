export const DMI_ATTRIBUTION =
  "Baseret på data fra DMI og efterfølgende bearbejdet" as const;

export type RadarBounds = [
  west: number,
  south: number,
  east: number,
  north: number,
];

export interface RadarFrame {
  id: string;
  observedAt: string;
  fetchedAt: string;
  url: string;
  bounds: RadarBounds;
  product: "DBZH";
  unit: "dBZ";
  sha256: string;
}

export interface RadarManifest {
  schemaVersion: 1;
  generatedAt: string;
  attribution: typeof DMI_ATTRIBUTION;
  frames: RadarFrame[];
}

export interface NowcastFrame {
  id: string;
  predictedAt: string;
  generatedAt: string;
  basedOnObservedAt: string;
  leadMinutes: number;
  url: string;
  bounds: RadarBounds;
  product: "DBZH_NOWCAST";
  unit: "dBZ";
  confidence: number;
  forecastMethod?: "optical-flow" | "persistence";
  validationSamples?: number;
  verificationCsi?: number | null;
  skillOverPersistence?: number | null;
  sha256: string;
}

export interface NowcastManifest {
  schemaVersion: 1;
  generatedAt: string;
  attribution: typeof DMI_ATTRIBUTION;
  method:
    | "adaptive-optical-flow-persistence"
    | "dense-optical-flow-extrapolation";
  basedOnObservedAt: string;
  sourceFrameCount: number;
  frames: NowcastFrame[];
}

export interface ForecastPoint {
  step: string;
  temperatureC: number | null;
  precipitationKgM2: number | null;
  windSpeedMs: number | null;
  cloudCoverPercent: number | null;
}

export interface ForecastResponse {
  latitude: number;
  longitude: number;
  fetchedAt: string;
  attribution: typeof DMI_ATTRIBUTION;
  source?: "dmi-edr" | "open-meteo-dmi";
  model?: "DMI HARMONIE AROME";
  points: ForecastPoint[];
}

export type RainIntensity = "none" | "trace" | "light" | "moderate" | "heavy";
export type RainPointSource = "radar-nowcast" | "harmonie";

export interface RainForecastPoint {
  startsAt: string;
  endsAt: string;
  precipitationMm: number;
  intensity: RainIntensity;
  source?: RainPointSource;
  reflectivityDbz?: number | null;
  confidence?: number | null;
  forecastMethod?: "optical-flow" | "persistence" | null;
}

export interface RainNextHourResponse {
  latitude: number;
  longitude: number;
  fetchedAt: string;
  attribution: typeof DMI_ATTRIBUTION;
  source: "dmi-edr" | "open-meteo-dmi" | "dmi-radar-nowcast-harmonie";
  model: "DMI HARMONIE AROME";
  displayResolutionMinutes: 15;
  sourceResolutionMinutes: 60;
  isInterpolated: true;
  basedOnObservedAt?: string;
  radarBasedUntil?: string;
  points: RainForecastPoint[];
}

export interface LocationResult {
  id: string;
  name: string;
  context: string;
  latitude: number;
  longitude: number;
  type: "address" | "place";
}

export interface LocationSearchResponse {
  query: string;
  results: LocationResult[];
}

export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  traceId?: string;
}

export const RADAR_SCALE = [
  { min: -10, color: "#77f4ff", label: "−10" },
  { min: 0, color: "#31b9f4", label: "0" },
  { min: 10, color: "#3478e5", label: "10" },
  { min: 20, color: "#56d46c", label: "20" },
  { min: 30, color: "#f2db4c", label: "30" },
  { min: 40, color: "#ff8b38", label: "40" },
  { min: 50, color: "#ed3e57", label: "50+" },
] as const;

export { WetMapApiClient, WetMapApiError } from "./client";
