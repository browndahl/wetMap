import { useEffect, useMemo, useState } from "react";
import { Bell, BellRing, Droplets, LoaderCircle } from "lucide-react";
import type {
  RainEta,
  RainForecastPoint,
  RainIntensity,
  RainNextHourResponse,
} from "@wetmap/shared";
import { translate } from "../i18n";
import {
  deletePushSubscription,
  getPushConfig,
  savePushSubscription,
} from "../api";

interface Props {
  compact?: boolean;
  data?: RainNextHourResponse;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  locale: "da" | "en";
  locationName: string;
  latitude: number;
  longitude: number;
}

const formatTime = (value: string, locale: "da" | "en") =>
  new Intl.DateTimeFormat(locale === "da" ? "da-DK" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Copenhagen",
  }).format(new Date(value));

const base64UrlToBytes = (value: string) => {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const binary = window.atob(
    (value + padding).replace(/-/g, "+").replace(/_/g, "/"),
  );
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
};

function deriveRainEta(points: RainForecastPoint[]): RainEta {
  const hasWeakEcho = points.some((point) => point.intensity === "trace");
  const wet = points.map((point) =>
    ["light", "moderate", "heavy"].includes(point.intensity),
  );
  const firstWet = wet.indexOf(true);
  const firstDryAfterRain = wet.findIndex(
    (isWet, index) => index > firstWet && !isWet,
  );
  let wetSegments = 0;
  wet.forEach((isWet, index) => {
    if (isWet && !wet[index - 1]) wetSegments += 1;
  });
  const order: RainIntensity[] = [
    "none",
    "trace",
    "light",
    "moderate",
    "heavy",
  ];
  const peakIntensity = points.reduce<RainIntensity>(
    (peak, point) =>
      order.indexOf(point.intensity) > order.indexOf(peak)
        ? point.intensity
        : peak,
    "none",
  );
  const relevantPoints = points.filter((point) =>
    firstWet >= 0
      ? ["light", "moderate", "heavy"].includes(point.intensity)
      : hasWeakEcho
        ? point.intensity === "trace"
        : true,
  );
  const confidences = relevantPoints
    .map((point) => point.confidence)
    .filter(
      (confidence): confidence is number =>
        confidence !== null &&
        confidence !== undefined &&
        Number.isFinite(confidence),
    );
  const confidence = confidences.length
    ? Math.round(
        (confidences.reduce((sum, value) => sum + value, 0) /
          confidences.length) *
          100,
      ) / 100
    : null;
  const sources = new Set(
    relevantPoints.map((point) => point.source ?? "harmonie"),
  );
  return {
    status:
      firstWet < 0
        ? hasWeakEcho
          ? "weak-echo"
          : "dry"
        : wetSegments > 1
          ? "intermittent"
          : firstWet === 0
            ? "raining"
            : "expected",
    arrivalWindowStart: firstWet > 0 ? points[firstWet].startsAt : null,
    arrivalWindowEnd: firstWet > 0 ? points[firstWet].endsAt : null,
    departureWindowStart:
      firstDryAfterRain > 0 ? points[firstDryAfterRain].startsAt : null,
    departureWindowEnd:
      firstDryAfterRain > 0 ? points[firstDryAfterRain].endsAt : null,
    continuesBeyondHorizon: firstWet >= 0 && firstDryAfterRain === -1,
    durationMinutes: wet.reduce(
      (minutes, isWet, index) =>
        isWet
          ? minutes +
            Math.max(
              0,
              (Date.parse(points[index].endsAt) -
                Date.parse(points[index].startsAt)) /
                60_000,
            )
          : minutes,
      0,
    ),
    totalPrecipitationMm:
      Math.round(
        points.reduce((sum, point) => sum + point.precipitationMm, 0) * 100,
      ) / 100,
    peakIntensity,
    confidence,
    confidenceLevel:
      confidence === null
        ? "unknown"
        : confidence >= 0.8
          ? "high"
          : confidence >= 0.55
            ? "medium"
            : "low",
    source:
      sources.size > 1
        ? "mixed"
        : sources.has("radar-nowcast")
          ? "radar-nowcast"
          : "harmonie",
  };
}

const intensityKey = (intensity: RainIntensity) =>
  ({
    none: "intensityNone",
    trace: "intensityTrace",
    light: "intensityLight",
    moderate: "intensityModerate",
    heavy: "intensityHeavy",
  })[intensity] as
    | "intensityNone"
    | "intensityTrace"
    | "intensityLight"
    | "intensityModerate"
    | "intensityHeavy";

export default function RainNextHour({
  compact = false,
  data,
  isLoading,
  isFetching,
  isError,
  locale,
  locationName,
  latitude,
  longitude,
}: Props) {
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  const [alertsEnabled, setAlertsEnabled] = useState(false);
  const [alertBusy, setAlertBusy] = useState(false);
  const [alertError, setAlertError] = useState(false);
  const points = useMemo(() => data?.points ?? [], [data?.points]);
  const rainEta = useMemo(
    () => data?.rainEta ?? deriveRainEta(points),
    [data?.rainEta, points],
  );
  const max = Math.max(...points.map((point) => point.precipitationMm), 0.1);
  const hasRadar = data?.source === "dmi-radar-nowcast-harmonie";
  const formatWindow = (start: string | null, end: string | null) =>
    start && end
      ? `${formatTime(start, locale)}–${formatTime(end, locale)}`
      : null;
  const arrivalWindow = formatWindow(
    rainEta.arrivalWindowStart,
    rainEta.arrivalWindowEnd,
  );
  const departureWindow = formatWindow(
    rainEta.departureWindowStart,
    rainEta.departureWindowEnd,
  );
  const etaHeadline =
    rainEta.status === "dry"
      ? t("rainDry")
      : rainEta.status === "weak-echo"
        ? t("rainWeakEcho")
        : rainEta.status === "raining"
          ? t("rainEtaRaining")
          : rainEta.status === "intermittent"
            ? t("rainIntermittent")
            : `${t("rainEtaExpected")} ${arrivalWindow ?? ""}`.trim();
  const confidenceKey =
    rainEta.confidenceLevel === "high"
      ? "rainEtaConfidenceHigh"
      : rainEta.confidenceLevel === "medium"
        ? "rainEtaConfidenceMedium"
        : rainEta.confidenceLevel === "low"
          ? "rainEtaConfidenceLow"
          : "rainEtaConfidenceUnknown";
  const sourceKey =
    rainEta.source === "radar-nowcast"
      ? "rainEtaSourceRadar"
      : rainEta.source === "mixed"
        ? "rainEtaSourceMixed"
        : "rainEtaSourceModel";
  const etaWindowText =
    rainEta.status === "intermittent"
      ? arrivalWindow
        ? `${t("rainEtaArrivalWindow")} ${arrivalWindow}`
        : null
      : rainEta.status === "raining" || rainEta.status === "expected"
        ? departureWindow
          ? `${t("rainEtaStopWindow")} ${departureWindow}`
          : rainEta.continuesBeyondHorizon
            ? t("rainEtaContinues")
            : null
        : null;

  useEffect(() => {
    let active = true;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => {
        if (active) setAlertsEnabled(Boolean(subscription));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!alertsEnabled || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => {
        if (subscription)
          return savePushSubscription(
            subscription,
            latitude,
            longitude,
            locationName,
            locale,
          );
      })
      .catch(() => setAlertError(true));
  }, [alertsEnabled, latitude, locale, locationName, longitude]);

  const toggleAlerts = async () => {
    setAlertError(false);
    setAlertBusy(true);
    if (alertsEnabled) {
      try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) {
          await deletePushSubscription(subscription.endpoint);
          await subscription.unsubscribe();
        }
        setAlertsEnabled(false);
      } catch {
        setAlertError(true);
      } finally {
        setAlertBusy(false);
      }
      return;
    }
    if (
      typeof Notification === "undefined" ||
      !("serviceWorker" in navigator) ||
      !("PushManager" in window)
    ) {
      setAlertError(true);
      setAlertBusy(false);
      return;
    }
    try {
      const permission =
        Notification.permission === "default"
          ? await Notification.requestPermission()
          : Notification.permission;
      if (permission !== "granted") throw new Error("Permission denied");
      const config = await getPushConfig();
      if (!config.available || !config.publicKey)
        throw new Error("Push is not configured");
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();
      const subscription =
        existing ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: base64UrlToBytes(config.publicKey),
        }));
      await savePushSubscription(
        subscription,
        latitude,
        longitude,
        locationName,
        locale,
      );
      setAlertsEnabled(true);
    } catch {
      setAlertError(true);
    } finally {
      setAlertBusy(false);
    }
  };

  return (
    <section className="rain-card" aria-labelledby="rain-title">
      <div className="rain-heading">
        <h3 id="rain-title">
          <Droplets size={15} aria-hidden="true" /> {t("rainNextHour")}
        </h3>
        <span>{t(hasRadar ? "radarModelEstimate" : "modelEstimate")}</span>
      </div>

      {isLoading && (
        <p className="rain-status muted" role="status">
          <LoaderCircle className="is-spinning" size={14} aria-hidden="true" />
          {t("loadingForecast")}
        </p>
      )}
      {isError && <p className="rain-status muted">{t("rainUnavailable")}</p>}
      {!isLoading && !isError && points.length === 0 && (
        <p className="rain-status muted">{t("rainUnavailable")}</p>
      )}

      {points.length > 0 && (
        <>
          <div className={`rain-eta is-${rainEta.status}`}>
            <span className="rain-eta-label">{t("rainEtaLabel")}</span>
            <div className="rain-summary">
              <strong>{etaHeadline}</strong>
              <span>
                {t("rainTotal")}{" "}
                {rainEta.totalPrecipitationMm.toFixed(
                  rainEta.totalPrecipitationMm < 1 ? 2 : 1,
                )}{" "}
                mm{isFetching ? " · …" : ""}
              </span>
            </div>
            {etaWindowText && (
              <p className="rain-eta-window">{etaWindowText}</p>
            )}
            <div className="rain-eta-meta">
              <span>{t(intensityKey(rainEta.peakIntensity))}</span>
              {rainEta.durationMinutes > 0 && (
                <span>
                  {rainEta.durationMinutes} {t("rainEtaDuration")}
                </span>
              )}
              <span>
                {t(confidenceKey)}
                {rainEta.confidence !== null
                  ? ` · ${Math.round(rainEta.confidence * 100)}%`
                  : ""}
              </span>
              <span>{t(sourceKey)}</span>
            </div>
            {!compact && (
              <details className="rain-eta-details">
                <summary>{t("rainEtaWhy")}</summary>
                <p>{t(hasRadar ? "rainRadarMethod" : "rainMethod")}</p>
                {data && (
                  <time dateTime={data.basedOnObservedAt ?? data.fetchedAt}>
                    {t("rainEtaUpdated")}{" "}
                    {formatTime(
                      data.basedOnObservedAt ?? data.fetchedAt,
                      locale,
                    )}
                  </time>
                )}
              </details>
            )}
          </div>
          {!compact && (
            <>
              <div className="rain-chart" aria-label={t("rainNextHour")}>
                {points.map((point) => (
                  <div className="rain-column" key={point.startsAt}>
                    <div
                      className={`rain-bar-track is-${point.intensity}`}
                      aria-hidden="true"
                    >
                      <strong className="rain-amount">
                        {point.precipitationMm.toLocaleString(
                          locale === "da" ? "da-DK" : "en-GB",
                          {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          },
                        )}
                        <small> mm</small>
                      </strong>
                      <span className="rain-intensity">
                        {t(intensityKey(point.intensity))}
                      </span>
                      <span
                        className={`rain-source is-${point.source ?? "harmonie"}`}
                        title={
                          point.source === "radar-nowcast"
                            ? `${t("radarSource")}${
                                point.reflectivityDbz == null
                                  ? ""
                                  : ` · ${point.reflectivityDbz} dBZ`
                              }${
                                point.forecastMethod
                                  ? ` · ${t(
                                      point.forecastMethod === "persistence"
                                        ? "nowcastPersistence"
                                        : point.forecastMethod ===
                                            "recall-calibrated-ensemble"
                                          ? "nowcastRecallCalibrated"
                                          : point.forecastMethod ===
                                              "probability-gated-ensemble"
                                            ? "nowcastProbabilityGated"
                                            : point.forecastMethod ===
                                                "regime-adaptive-ensemble"
                                              ? "nowcastAdaptiveEnsemble"
                                              : point.forecastMethod ===
                                                  "trajectory-speed-corrected"
                                                ? "nowcastSpeedCorrected"
                                                : point.forecastMethod ===
                                                    "trajectory-optical-flow"
                                                  ? "nowcastTrajectory"
                                                  : "nowcastOpticalFlow",
                                    )}`
                                  : ""
                              }`
                            : t("modelSource")
                        }
                      >
                        {point.source === "radar-nowcast"
                          ? `${t("radarSource")}${
                              point.reflectivityDbz == null
                                ? ""
                                : ` · ${point.reflectivityDbz}`
                            }`
                          : t("modelSource")}
                      </span>
                      <span
                        className={`rain-bar is-${point.intensity}`}
                        style={{
                          height: `${Math.max(
                            point.intensity === "none" ? 4 : 16,
                            (point.precipitationMm / max) * 62,
                          )}%`,
                        }}
                      />
                    </div>
                    <time dateTime={point.startsAt}>
                      {formatTime(point.startsAt, locale)}
                    </time>
                    <span className="sr-only">
                      {t(intensityKey(point.intensity))}:{" "}
                      {point.precipitationMm} mm
                    </span>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className={`rain-alert ${alertsEnabled ? "is-active" : ""}`}
                onClick={toggleAlerts}
                aria-pressed={alertsEnabled}
                disabled={alertBusy}
              >
                {alertsEnabled ? (
                  <BellRing size={14} aria-hidden="true" />
                ) : (
                  <Bell size={14} aria-hidden="true" />
                )}
                {alertBusy
                  ? t("rainAlertWorking")
                  : alertsEnabled
                    ? t("rainAlertOn")
                    : t("notifyRain")}
              </button>
              <p className={`rain-alert-note ${alertError ? "is-error" : ""}`}>
                {alertError ? t("rainAlertDenied") : t("rainAlertBackground")}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
