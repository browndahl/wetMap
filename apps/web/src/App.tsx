import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  Clock3,
  CloudRain,
  Languages,
  Layers3,
  Pause,
  Play,
  Radio,
  SkipForward,
  Wind,
} from "lucide-react";
import {
  DMI_ATTRIBUTION,
  RADAR_SCALE,
  type NowcastFrame,
  type RadarFrame,
} from "@wetmap/shared";
import {
  getForecast,
  getRadarManifest,
  getRadarNowcast,
  getRainNextHour,
} from "./api";
import { translate } from "./i18n";
import { useWeatherStore } from "./store";
import LocationSearch from "./components/LocationSearch";
import PrecisionObservatory from "./components/PrecisionObservatory";
import RainNextHour from "./components/RainNextHour";
import { useCompactLayout } from "./useCompactLayout";

const WeatherMap = lazy(() => import("./components/WeatherMap"));
const radarDelayBudgetMinutes = 25;

const isNowcastFrame = (
  frame: RadarFrame | NowcastFrame | undefined,
): frame is NowcastFrame => Boolean(frame && "predictedAt" in frame);

const radarFrameTime = (frame: RadarFrame | NowcastFrame) =>
  isNowcastFrame(frame) ? frame.predictedAt : frame.observedAt;

const formatTime = (value: string | number, locale: "da" | "en") =>
  new Intl.DateTimeFormat(locale === "da" ? "da-DK" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Copenhagen",
  }).format(new Date(value));

const formatAge = (minutes: number, locale: "da" | "en") => {
  if (minutes < 1) return locale === "da" ? "nu" : "now";
  return locale === "da" ? `${minutes} min siden` : `${minutes} min ago`;
};

const timelineStartsCollapsed = () => {
  try {
    const stored = window.localStorage.getItem("wetmap:timeline-collapsed");
    if (stored !== null) return stored === "true";
  } catch {
    // Use the layout default if browser storage is unavailable.
  }
  return window.matchMedia?.("(max-width: 850px)").matches ?? false;
};

export default function App() {
  const state = useWeatherStore();
  const compactLayout = useCompactLayout();
  const [forecastExpanded, setForecastExpanded] = useState(false);
  const initialRadarPlaybackStarted = useRef(false);
  const [now, setNow] = useState(() => Date.now());
  const [timelineCollapsed, setTimelineCollapsed] = useState(
    timelineStartsCollapsed,
  );
  const forecastLatitude = Number(state.selectedLocation.latitude.toFixed(2));
  const forecastLongitude = Number(state.selectedLocation.longitude.toFixed(2));
  const rainLatitude = Number(state.selectedLocation.latitude.toFixed(5));
  const rainLongitude = Number(state.selectedLocation.longitude.toFixed(5));
  const manifest = useQuery({
    queryKey: ["radar-frames"],
    queryFn: ({ signal }) => getRadarManifest(signal),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
  });
  const nowcast = useQuery({
    queryKey: ["radar-nowcast"],
    queryFn: ({ signal }) => getRadarNowcast(signal),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
  });
  const forecast = useQuery({
    queryKey: ["forecast", forecastLatitude, forecastLongitude],
    queryFn: ({ signal }) =>
      getForecast(forecastLatitude, forecastLongitude, signal),
    staleTime: 10 * 60_000,
    gcTime: 6 * 60 * 60_000,
    retry: 3,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4_000),
    refetchInterval: 10 * 60_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
    placeholderData: keepPreviousData,
  });
  const rain = useQuery({
    queryKey: ["rain-next-hour", rainLatitude, rainLongitude],
    queryFn: ({ signal }) =>
      getRainNextHour(rainLatitude, rainLongitude, signal),
    staleTime: 60_000,
    gcTime: 60 * 60_000,
    retry: 3,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4_000),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
  });
  const frames = manifest.data?.frames ?? [];
  const latestObservationIndex = Math.max(frames.length - 1, 0);
  const latestFrame = frames[latestObservationIndex];
  const nowcastMatchesLatestObservation =
    latestFrame && nowcast.data
      ? Math.abs(
          Date.parse(nowcast.data.basedOnObservedAt) -
            Date.parse(latestFrame.observedAt),
        ) <=
        10 * 60_000
      : false;
  const nowcastFrames = nowcastMatchesLatestObservation
    ? (nowcast.data?.frames ?? []).filter(
        (frame) => Date.parse(frame.predictedAt) > now,
      )
    : [];
  const radarFrames: Array<RadarFrame | NowcastFrame> = [
    ...frames,
    ...nowcastFrames,
  ];
  const lastFrameIndex = Math.max(radarFrames.length - 1, 0);
  const safeIndex =
    state.selectedFrame < 0
      ? latestObservationIndex
      : Math.min(state.selectedFrame, lastFrameIndex);
  const activeFrame = radarFrames[safeIndex];
  const activeIsNowcast = isNowcastFrame(activeFrame);
  const activeFrameTime = activeFrame ? radarFrameTime(activeFrame) : undefined;
  const t = (key: Parameters<typeof translate>[1]) =>
    translate(state.locale, key);
  const ageMinutes = latestFrame
    ? Math.max(
        0,
        Math.floor((now - new Date(latestFrame.observedAt).getTime()) / 60_000),
      )
    : Infinity;
  const isStale = ageMinutes > radarDelayBudgetMinutes;
  const activeAgeMinutes = activeFrameTime
    ? Math.max(
        0,
        Math.floor((now - new Date(activeFrameTime).getTime()) / 60_000),
      )
    : 0;
  const currentHour = new Date(now);
  currentHour.setMinutes(0, 0, 0);
  const forecastPoints = (forecast.data?.points ?? [])
    .filter((point) => new Date(point.step).getTime() >= currentHour.getTime())
    .slice(0, 4);

  useEffect(() => {
    let minuteTimer: number | undefined;
    const nextMinute = window.setTimeout(
      () => {
        setNow(Date.now());
        minuteTimer = window.setInterval(() => setNow(Date.now()), 60_000);
      },
      60_000 - (Date.now() % 60_000),
    );
    return () => {
      window.clearTimeout(nextMinute);
      if (minuteTimer !== undefined) window.clearInterval(minuteTimer);
    };
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        "wetmap:timeline-collapsed",
        String(timelineCollapsed),
      );
    } catch {
      // Storage can be unavailable in hardened/private browser contexts.
    }
  }, [timelineCollapsed]);

  useEffect(() => {
    if (!state.playing || radarFrames.length < 2) return;
    if (safeIndex >= lastFrameIndex) {
      state.setPlaying(false);
      return;
    }
    const timer = window.setTimeout(
      () => state.setSelectedFrame(safeIndex + 1),
      700,
    );
    return () => window.clearTimeout(timer);
  }, [lastFrameIndex, radarFrames.length, safeIndex, state]);

  useEffect(() => {
    if (
      radarFrames.length &&
      (state.selectedFrame < 0 || state.selectedFrame >= radarFrames.length)
    ) {
      const reducedMotion =
        window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ??
        false;
      if (
        radarFrames.length > 1 &&
        !reducedMotion &&
        !initialRadarPlaybackStarted.current
      ) {
        initialRadarPlaybackStarted.current = true;
        state.setSelectedFrame(Math.max(0, latestObservationIndex - 6));
        state.setPlaying(true);
      } else {
        state.setSelectedFrame(latestObservationIndex);
      }
    }
  }, [latestObservationIndex, radarFrames.length, state]);

  const togglePlayback = () => {
    if (state.playing) {
      state.setPlaying(false);
      return;
    }
    if (safeIndex >= lastFrameIndex)
      state.setSelectedFrame(Math.max(0, latestObservationIndex - 6));
    state.setPlaying(true);
  };

  return (
    <main className="app-shell">
      <a className="skip-link" href="#weather-panel">
        {t("skipToWeather")}
      </a>
      <Suspense
        fallback={
          <div className="map-loading" role="status">
            {t("loadingMap")}
          </div>
        }
      >
        <WeatherMap frames={radarFrames} activeIndex={safeIndex} />
      </Suspense>

      <header className="topbar glass" aria-label="WetMap">
        <div className="brand-mark" aria-hidden="true">
          <CloudRain size={19} />
        </div>
        <div>
          <strong>wetmap</strong>
          <span>
            {state.selectedLocation.name} · {forecastLatitude.toFixed(2)}°n
          </span>
        </div>
        <span
          className={`freshness ${isStale ? "is-stale" : ""}`}
          role="status"
          title={t("freshnessHelp")}
        >
          <Radio size={13} aria-hidden="true" />
          {isStale ? t("stale") : t("fresh")} ·{" "}
          {Number.isFinite(ageMinutes)
            ? formatAge(ageMinutes, state.locale)
            : "–"}
        </span>
        <button
          className="icon-button"
          aria-label={t("language")}
          onClick={() => state.setLocale(state.locale === "da" ? "en" : "da")}
        >
          <Languages size={18} aria-hidden="true" />
          <span>{state.locale.toUpperCase()}</span>
        </button>
      </header>

      <LocationSearch />
      <PrecisionObservatory locale={state.locale} />

      <div className="weather-dock">
        <section
          id="weather-panel"
          className="weather-card glass"
          aria-labelledby={
            compactLayout ? "mobile-forecast-title" : "forecast-title"
          }
          tabIndex={-1}
        >
          {compactLayout && (
            <button
              className="forecast-toggle"
              aria-label={
                forecastExpanded ? t("collapseForecast") : t("expandForecast")
              }
              aria-expanded={forecastExpanded}
              aria-controls="forecast-details"
              onClick={() => {
                setForecastExpanded(!forecastExpanded);
                if (!forecastExpanded) setTimelineCollapsed(true);
              }}
            >
              <span>
                <strong id="mobile-forecast-title">
                  {state.selectedLocation.name}
                </strong>
                <span>{t("rainNextHour")}</span>
              </span>
              {forecastExpanded ? (
                <ChevronDown aria-hidden="true" />
              ) : (
                <ChevronUp aria-hidden="true" />
              )}
            </button>
          )}
          <div
            id="forecast-details"
            hidden={compactLayout && !forecastExpanded}
          >
            <div className="eyebrow">
              <Wind size={15} aria-hidden="true" /> DMI HARMONIE
              {forecast.isFetching && !forecast.isLoading && (
                <span role="status"> · {t("updatingForecast")}</span>
              )}
            </div>
            <h2 id="forecast-title">{t("forecast")}</h2>
            {forecast.isLoading && (
              <p className="muted" role="status">
                {t("loadingForecast")}
              </p>
            )}
            {forecast.isError && (
              <p className="muted">{t("forecastUnavailable")}</p>
            )}
            {!forecast.isLoading &&
              !forecast.isError &&
              forecastPoints.length === 0 && (
                <p className="muted">{t("forecastUnavailable")}</p>
              )}
            {forecastPoints.map((point) => (
              <div className="forecast-row" key={point.step}>
                <time dateTime={point.step}>
                  {new Date(point.step).getTime() <
                  currentHour.getTime() + 3_600_000
                    ? t("now")
                    : formatTime(point.step, state.locale)}
                </time>
                <strong>
                  {point.temperatureC == null
                    ? "–"
                    : `${Math.round(point.temperatureC)}°`}
                </strong>
                <span>
                  {point.windSpeedMs == null
                    ? "–"
                    : `${point.windSpeedMs.toFixed(1)} m/s`}
                </span>
              </div>
            ))}
          </div>
          <RainNextHour
            compact={compactLayout && !forecastExpanded}
            data={rain.data}
            isLoading={rain.isLoading}
            isFetching={rain.isFetching}
            isError={rain.isError}
            locale={state.locale}
            locationName={state.selectedLocation.name}
            latitude={state.selectedLocation.latitude}
            longitude={state.selectedLocation.longitude}
          />
        </section>

        <aside className="legend glass" aria-label={t("reflectivity")}>
          <strong>{t("reflectivity")}</strong>
          <div className="legend-scale" aria-hidden="true">
            {RADAR_SCALE.map((entry) => (
              <span key={entry.min} style={{ backgroundColor: entry.color }} />
            ))}
          </div>
          <div className="legend-labels">
            <span>−10</span>
            <span>20</span>
            <span>50+</span>
          </div>
        </aside>

        <section
          className={`timeline glass ${timelineCollapsed ? "is-collapsed" : ""}`}
          aria-labelledby="timeline-title"
        >
          <div className="timeline-heading">
            <div>
              <span className="eyebrow">
                {activeIsNowcast
                  ? `${t("nowcast")} · +${activeFrame.leadMinutes} min`
                  : safeIndex === latestObservationIndex
                    ? t("latestObservation")
                    : t("observed")}
              </span>
              <h1 id="timeline-title">
                {activeFrameTime
                  ? formatTime(activeFrameTime, state.locale)
                  : t("radar")}
              </h1>
            </div>
            <div className="timeline-actions">
              <button
                className="timeline-toggle"
                onClick={() => {
                  setTimelineCollapsed(!timelineCollapsed);
                  if (compactLayout && timelineCollapsed)
                    setForecastExpanded(false);
                }}
                aria-label={
                  timelineCollapsed
                    ? t("expandTimeline")
                    : t("collapseTimeline")
                }
                aria-expanded={!timelineCollapsed}
                aria-controls="timeline-details"
              >
                {timelineCollapsed ? (
                  <ChevronUp aria-hidden="true" />
                ) : (
                  <ChevronDown aria-hidden="true" />
                )}
              </button>
              <div className="live-clock">
                <span>{t("now")}</span>
                <time dateTime={new Date(now).toISOString()}>
                  {formatTime(now, state.locale)}
                </time>
              </div>
              <button
                className="play-button"
                onClick={togglePlayback}
                aria-label={state.playing ? t("pause") : t("play")}
                disabled={radarFrames.length < 2}
              >
                {state.playing ? (
                  <Pause aria-hidden="true" />
                ) : (
                  <Play aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          {!timelineCollapsed && (
            <div id="timeline-details">
              {radarFrames.length ? (
                <>
                  <div className="timeline-context">
                    {activeIsNowcast ? (
                      <>
                        <span>
                          <Clock3 size={14} aria-hidden="true" />
                          {t("nowcastBasedOn")}{" "}
                          {formatTime(
                            activeFrame.basedOnObservedAt,
                            state.locale,
                          )}
                        </span>
                        <span className="timeline-gap">
                          {t("nowcastConfidence")}{" "}
                          {Math.round(activeFrame.confidence * 100)}%
                          {activeFrame.forecastMethod
                            ? ` · ${t(
                                activeFrame.forecastMethod === "persistence"
                                  ? "nowcastPersistence"
                                  : activeFrame.forecastMethod ===
                                      "recall-calibrated-ensemble"
                                    ? "nowcastRecallCalibrated"
                                    : activeFrame.forecastMethod ===
                                        "probability-gated-ensemble"
                                      ? "nowcastProbabilityGated"
                                      : activeFrame.forecastMethod ===
                                          "regime-adaptive-ensemble"
                                        ? "nowcastAdaptiveEnsemble"
                                        : activeFrame.forecastMethod ===
                                            "trajectory-speed-corrected"
                                          ? "nowcastSpeedCorrected"
                                          : activeFrame.forecastMethod ===
                                              "trajectory-optical-flow"
                                            ? "nowcastTrajectory"
                                            : "nowcastOpticalFlow",
                              )}`
                            : ""}
                        </span>
                      </>
                    ) : (
                      <>
                        <span>
                          <Clock3 size={14} aria-hidden="true" />
                          {t("measured")}{" "}
                          {formatTime(activeFrame.observedAt, state.locale)}
                        </span>
                        <span className="timeline-gap">
                          {activeAgeMinutes} {t("minutesBehindNow")}
                        </span>
                      </>
                    )}
                    {safeIndex !== latestObservationIndex && (
                      <button
                        type="button"
                        onClick={() =>
                          state.setSelectedFrame(latestObservationIndex)
                        }
                      >
                        <SkipForward size={14} aria-hidden="true" />
                        {t("jumpToLatest")}
                      </button>
                    )}
                  </div>
                  <input
                    className="scrubber"
                    type="range"
                    min="0"
                    max={Math.max(radarFrames.length - 1, 0)}
                    value={safeIndex}
                    onChange={(event) => {
                      state.setPlaying(false);
                      state.setSelectedFrame(Number(event.target.value));
                    }}
                    aria-label={t("radarTime")}
                    aria-valuetext={
                      activeFrameTime
                        ? formatTime(activeFrameTime, state.locale)
                        : undefined
                    }
                  />
                  <div className="timeline-ticks">
                    <time dateTime={frames[0].observedAt}>
                      {formatTime(frames[0].observedAt, state.locale)}
                    </time>
                    <span>
                      {nowcastFrames.length
                        ? t("nowcastTimeline")
                        : t("observedHistory")}
                    </span>
                    <time dateTime={radarFrameTime(radarFrames.at(-1)!)}>
                      {formatTime(
                        radarFrameTime(radarFrames.at(-1)!),
                        state.locale,
                      )}
                    </time>
                  </div>
                  <p className="timeline-note">
                    {nowcastFrames.length
                      ? t("nowcastNote")
                      : t("futureRadarNote")}
                  </p>
                </>
              ) : (
                <div className="empty-state" role="status">
                  <strong>{t("noData")}</strong>
                  <span>{t("noDataDetail")}</span>
                </div>
              )}

              <div className="control-grid">
                <label>
                  <span>
                    {t("opacity")}{" "}
                    <output>{Math.round(state.opacity * 100)}%</output>
                  </span>
                  <input
                    type="range"
                    min="0.1"
                    max="1"
                    step="0.05"
                    value={state.opacity}
                    onChange={(e) => state.setOpacity(Number(e.target.value))}
                  />
                </label>
                <button
                  className={`mode-button ${state.precise2d ? "is-active" : ""}`}
                  onClick={() => state.setPrecise2d(!state.precise2d)}
                  aria-pressed={state.precise2d}
                >
                  <Layers3 size={17} aria-hidden="true" />{" "}
                  {state.precise2d ? t("precise") : t("buildings")}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      <footer className="attribution">
        <a href="https://www.dmi.dk/friedata" target="_blank" rel="noreferrer">
          {DMI_ATTRIBUTION}
        </a>
        {(forecast.data?.source === "open-meteo-dmi" ||
          rain.data?.source === "open-meteo-dmi") && (
          <span>
            {" "}
            ·{" "}
            <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
              Open-Meteo
            </a>
          </span>
        )}
        {activeFrame && (
          <span>
            {" "}
            · {t("fetched")}{" "}
            <time
              dateTime={
                isNowcastFrame(activeFrame)
                  ? activeFrame.generatedAt
                  : activeFrame.fetchedAt
              }
            >
              {formatTime(
                isNowcastFrame(activeFrame)
                  ? activeFrame.generatedAt
                  : activeFrame.fetchedAt,
                state.locale,
              )}
            </time>
          </span>
        )}
        <span> · © OpenStreetMap · OpenFreeMap</span>
      </footer>
    </main>
  );
}
