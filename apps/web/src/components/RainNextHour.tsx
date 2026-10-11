import { useEffect, useMemo, useState } from "react";
import { Bell, BellRing, Droplets, LoaderCircle } from "lucide-react";
import type {
  RainForecastPoint,
  RainIntensity,
  RainNextHourResponse,
} from "@wetmap/shared";
import { translate } from "../i18n";

interface Props {
  data?: RainNextHourResponse;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  locale: "da" | "en";
  locationName: string;
}

const alertPreferenceKey = "wetmap:rain-alerts";
const lastAlertKey = "wetmap:last-rain-alert";

const formatTime = (value: string, locale: "da" | "en") =>
  new Intl.DateTimeFormat(locale === "da" ? "da-DK" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Copenhagen",
  }).format(new Date(value));

const startsEnabled = () => {
  try {
    return window.localStorage.getItem(alertPreferenceKey) === "true";
  } catch {
    return false;
  }
};

function summary(points: RainForecastPoint[]): {
  key:
    | "rainDry"
    | "rainStarts"
    | "rainStops"
    | "rainContinues"
    | "rainIntermittent";
  at?: string;
} {
  const wet = points.map((point) => point.intensity !== "none");
  const firstWet = wet.indexOf(true);
  if (firstWet === -1) return { key: "rainDry" };
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
    light: "intensityLight",
    moderate: "intensityModerate",
    heavy: "intensityHeavy",
  })[intensity] as
    | "intensityNone"
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
}: Props) {
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  const [alertsEnabled, setAlertsEnabled] = useState(startsEnabled);
  const [alertError, setAlertError] = useState(false);
  const points = useMemo(() => data?.points ?? [], [data?.points]);
  const rainSummary = useMemo(() => summary(points), [points]);
  const total = points.reduce((sum, point) => sum + point.precipitationMm, 0);
  const max = Math.max(...points.map((point) => point.precipitationMm), 0.1);

  useEffect(() => {
    if (
      !alertsEnabled ||
      typeof Notification === "undefined" ||
      Notification.permission !== "granted"
    )
      return;
    const firstWet = points.find((point) => point.intensity !== "none");
    if (!firstWet) return;
    const eventKey = `${locationName}:${firstWet.startsAt}`;
    try {
      if (window.localStorage.getItem(lastAlertKey) === eventKey) return;
      new Notification(translate(locale, "rainAlertTitle"), {
        body: `${translate(locale, "rainAlertBody")} ${locationName} ${formatTime(firstWet.startsAt, locale)}.`,
        tag: "wetmap-rain",
      });
      window.localStorage.setItem(lastAlertKey, eventKey);
    } catch {
      // Notifications and storage can be unavailable in hardened contexts.
    }
  }, [alertsEnabled, locale, locationName, points]);

  const toggleAlerts = async () => {
    setAlertError(false);
    if (alertsEnabled) {
      setAlertsEnabled(false);
      try {
        window.localStorage.setItem(alertPreferenceKey, "false");
      } catch {
        // Preference remains session-only when storage is unavailable.
      }
      return;
    }
    if (typeof Notification === "undefined") {
      setAlertError(true);
      return;
    }
    const permission =
      Notification.permission === "default"
        ? await Notification.requestPermission()
        : Notification.permission;
    if (permission !== "granted") {
      setAlertError(true);
      return;
    }
    setAlertsEnabled(true);
    try {
      window.localStorage.setItem(alertPreferenceKey, "true");
    } catch {
      // Preference remains session-only when storage is unavailable.
    }
  };

  return (
    <section className="rain-card" aria-labelledby="rain-title">
      <div className="rain-heading">
        <h3 id="rain-title">
          <Droplets size={15} aria-hidden="true" /> {t("rainNextHour")}
        </h3>
        <span>{t("modelEstimate")}</span>
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
          <p className="rain-method">{t("rainMethod")}</p>
          <button
            type="button"
            className={`rain-alert ${alertsEnabled ? "is-active" : ""}`}
            onClick={toggleAlerts}
            aria-pressed={alertsEnabled}
          >
            {alertsEnabled ? (
              <BellRing size={14} aria-hidden="true" />
            ) : (
              <Bell size={14} aria-hidden="true" />
            )}
            {alertsEnabled ? t("rainAlertOn") : t("notifyRain")}
          </button>
          <p className={`rain-alert-note ${alertError ? "is-error" : ""}`}>
            {alertError ? t("rainAlertDenied") : t("rainAlertOpenOnly")}
          </p>
        </>
      )}
    </section>
  );
}
