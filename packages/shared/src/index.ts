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
  forecastMethod?:
    | "optical-flow"
    | "persistence"
    | "trajectory-optical-flow"
    | "trajectory-speed-corrected"
    | "regime-adaptive-ensemble"
    | "probability-gated-ensemble";
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
  algorithmVersion?: string;
  rainThresholdDbz?: 5 | 10 | 15 | 20;
  rainRadiusPixels?: 1 | 3 | 5;
  basedOnObservedAt: string;
  sourceFrameCount: number;
  frames: NowcastFrame[];
}

export type PrecisionStatus =
  | "collecting"
  | "awaiting-rain"
  | "verified"
  | "degraded";

export interface VerificationSummary {
  sampleCount: number;
  validPixels: number;
  hits: number;
  misses: number;
  falseAlarms: number;
  precision: number | null;
  recall: number | null;
  criticalSuccessIndex: number | null;
  meanDbzMeanAbsoluteError: number | null;
  meanCriticalSuccessIndexSkill: number | null;
  meanPersistenceCriticalSuccessIndex?: number | null;
  meanBrierScore?: number | null;
  meanPersistenceBrierScore?: number | null;
  meanBrierSkillScore?: number | null;
}

export interface PrecisionHorizon extends VerificationSummary {
  targetLeadMinutes: 15 | 30 | 45 | 60;
  windowStartMinutes: number;
  windowEndMinutes: number;
  status: PrecisionStatus;
  meetsQualityGate: boolean;
  eventPixelCount: number;
  falseAlarmRate: number | null;
  missRate: number | null;
}

export interface PrecisionObservatory {
  schemaVersion: 1;
  thresholdDbz: number;
  overallStatus: PrecisionStatus;
  targetHorizonMinutes: Array<15 | 30 | 45 | 60>;
  qualityGate: {
    minimumSamples: number;
    minimumEventPixels: number;
    minimumCriticalSuccessIndex: number;
    minimumSkillOverPersistence: number;
  };
  verifiedHorizonCount: number;
  horizons: PrecisionHorizon[];
}

export type ShadowCandidateStatus =
  | "collecting"
  | "awaiting-rain"
  | "promotable"
  | "held-back";

export interface ShadowCandidateLeadQuality extends VerificationSummary {
  leadMinutes: number;
  status: ShadowCandidateStatus;
  safeToPromote: boolean;
  eventPixelCount: number;
  falseAlarmRate: number | null;
  baselineFalseAlarmRate: number | null;
  falseAlarmRateIncrease: number | null;
  baselineCriticalSuccessIndex: number | null;
  criticalSuccessIndexImprovement: number | null;
  minimumRainProbability?: number | null;
}

export interface ShadowCandidateQuality {
  candidateId: string;
  forecastMethod: string;
  minimumLeadMinutes: number;
  promotionGate: {
    minimumSamples: number;
    minimumEventPixels: number;
    minimumCriticalSuccessIndex: number;
    minimumCriticalSuccessIndexImprovement: number;
    minimumSkillOverPersistence: number;
    maximumFalseAlarmRateIncrease: number;
    minimumBrierSkillOverPersistence?: number | null;
  };
  safeToPromoteLeadMinutes: number[];
  byLeadMinutes: ShadowCandidateLeadQuality[];
}

export interface GroundGaugeQuality {
  observationCount: number;
  stationComparisonCount: number;
  hits: number;
  misses: number;
  falseAlarms: number;
  precision: number | null;
  recall: number | null;
  criticalSuccessIndex: number | null;
  calibration?: RadarThresholdCalibration;
}

export interface GeographicConsistencyQuality {
  schemaVersion: 1;
  generatedAt: string;
  basedOnObservedAt: string;
  status: "verified" | "degraded";
  rainThresholdDbz: 5 | 10 | 15 | 20;
  spatialRadiusPixels: 1 | 3 | 5;
  locationCount: number;
  frameCount: number;
  comparisonCount: number;
  valueMismatchCount: number;
  rainClassificationMismatchCount: number;
  maximumReflectivityDifferenceDbz: number;
  locations: string[];
  mismatchExamples: Array<{
    location: string;
    latitude: number;
    longitude: number;
    leadMinutes: number;
    mapReflectivityDbz: number | null;
    pointReflectivityDbz: number | null;
  }>;
}

export type RadarCalibrationStatus =
  | "collecting"
  | "awaiting-overlap"
  | "inconclusive"
  | "calibrated";

export interface RadarCalibrationCandidate {
  thresholdDbz: 5 | 10 | 15 | 20;
  spatialRadiusPixels: 1 | 3 | 5;
  hits: number;
  misses: number;
  falseAlarms: number;
  correctNegatives: number;
  wetEventCount: number;
  radarEventCount: number;
  precision: number | null;
  recall: number | null;
  criticalSuccessIndex: number | null;
  falseAlarmRate: number | null;
  missRate: number | null;
  eligible: boolean;
}

export interface RadarThresholdCalibration {
  schemaVersion: 1;
  status: RadarCalibrationStatus;
  safeToPromote: boolean;
  minimumObservationCount: number;
  minimumWetEventCount: number;
  minimumRadarEventCount: number;
  minimumHitCount: number;
  minimumCriticalSuccessIndex: number;
  minimumCriticalSuccessIndexImprovement: number;
  observationCount: number;
  forecastQualityStatus: PrecisionStatus;
  recommendedThresholdDbz: 5 | 10 | 15 | 20 | null;
  recommendedSpatialRadiusPixels: 1 | 3 | 5 | null;
  criticalSuccessIndexImprovement: number | null;
  appliedThresholdDbz: 5 | 10 | 15 | 20;
  appliedSpatialRadiusPixels: 1 | 3 | 5;
  candidates: RadarCalibrationCandidate[];
}

export interface NowcastQualityResponse {
  schemaVersion: number;
  generatedAt: string;
  latestVerifiedAt?: string | null;
  algorithmVersion: string;
  thresholdDbz: number;
  sampleCount: number;
  totalSampleCount: number;
  meanCriticalSuccessIndex: number | null;
  meanCriticalSuccessIndexSkill: number | null;
  observatory?: PrecisionObservatory;
  shadowCandidates?: ShadowCandidateQuality[];
  groundGauge?: GroundGaugeQuality;
  geographicConsistency?: GeographicConsistencyQuality;
}

export interface PrecisionObservatoryResponse {
  schemaVersion: number;
  generatedAt: string;
  latestVerifiedAt: string | null;
  algorithmVersion: string;
  thresholdDbz: number;
  sampleCount: number;
  totalSampleCount: number;
  observatory?: PrecisionObservatory;
  shadowCandidates?: ShadowCandidateQuality[];
  groundGauge?: GroundGaugeQuality;
  geographicConsistency?: GeographicConsistencyQuality;
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
export type RainEtaStatus =
  | "dry"
  | "weak-echo"
  | "raining"
  | "expected"
  | "intermittent";
export type RainEtaConfidenceLevel = "unknown" | "low" | "medium" | "high";
export type RainEtaSource = "radar-nowcast" | "harmonie" | "mixed";

export interface RainForecastPoint {
  startsAt: string;
  endsAt: string;
  precipitationMm: number;
  intensity: RainIntensity;
  source?: RainPointSource;
  reflectivityDbz?: number | null;
  confidence?: number | null;
  forecastMethod?:
    | "optical-flow"
    | "persistence"
    | "trajectory-optical-flow"
    | "trajectory-speed-corrected"
    | "regime-adaptive-ensemble"
    | "probability-gated-ensemble"
    | null;
}

export interface RainEta {
  status: RainEtaStatus;
  arrivalWindowStart: string | null;
  arrivalWindowEnd: string | null;
  departureWindowStart: string | null;
  departureWindowEnd: string | null;
  continuesBeyondHorizon: boolean;
  durationMinutes: number;
  totalPrecipitationMm: number;
  peakIntensity: RainIntensity;
  confidence: number | null;
  confidenceLevel: RainEtaConfidenceLevel;
  source: RainEtaSource;
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
  rainEta?: RainEta;
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
