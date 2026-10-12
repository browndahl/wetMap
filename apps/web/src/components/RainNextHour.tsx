import { useEffect, useMemo, useState } from "react";
import { Bell, BellRing, Droplets, LoaderCircle } from "lucide-react";
import type {
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

function summary(points: RainForecastPoint[]): {
  key:
    | "rainDry"
    | "rainWeakEcho"
    | "rainStarts"
    | "rainStops"
    | "rainContinues"
    | "rainIntermittent";
  at?: string;
} {
  const hasWeakEcho = points.some((point) => point.intensity === "trace");
  const wet = points.map((point) =>
    ["light", "moderate", "heavy"].includes(point.intensity),
  );
  const firstWet = wet.indexOf(true);
  if (firstWet === -1) return { key: hasWeakEcho ? "rainWeakEcho" : "rainDry" };
  if (wet.every(Boolean)) return { key: "rainContinues" };

  const firstDryAfterRain = wet.findIndex(
    (isWet, index) => index > firstWet && !isWet,
  );
  if (firstWet === 0 && firstDryAfterRain > 0)
    return { key: "rainStops", at: points[firstDryAfterRain].startsAt };
  if (
    firstWet > 0 &&
    (firstDryAfterRain === -1 || wet.slice(firstWet).every(Boolean))
  )
    return { key: "rainStarts", at: points[firstWet].startsAt };
  return { key: "rainIntermittent" };
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
  const rainSummary = useMemo(() => summary(points), [points]);
  const total = points.reduce((sum, point) => sum + point.precipitationMm, 0);
  const max = Math.max(...points.map((point) => point.precipitationMm), 0.1);
  const hasRadar = data?.source === "dmi-radar-nowcast-harmonie";

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
          <div className="rain-summary">
            <strong>
              {t(rainSummary.key)}
              {rainSummary.at ? ` ${formatTime(rainSummary.at, locale)}` : ""}
            </strong>
            <span>
              {t("rainTotal")} {total.toFixed(total < 1 ? 2 : 1)} mm
              {isFetching ? " · …" : ""}
            </span>
          </div>
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
                  {t(intensityKey(point.intensity))}: {point.precipitationMm} mm
                </span>
              </div>
            ))}
          </div>
          <p className="rain-method">
            {t(hasRadar ? "rainRadarMethod" : "rainMethod")}
          </p>
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
    </section>
  );
}
