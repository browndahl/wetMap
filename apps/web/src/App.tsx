import { lazy, Suspense, useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CloudRain, Languages, Layers3, Pause, Play, Radio, Wind } from "lucide-react";
import { DMI_ATTRIBUTION, RADAR_SCALE } from "@wetmap/shared";
import { getForecast, getRadarManifest } from "./api";
import { translate } from "./i18n";
import { useWeatherStore } from "./store";

const WeatherMap = lazy(() => import("./components/WeatherMap"));
const radarDelayBudgetMinutes = 25;

const formatTime = (value: string | number, locale: "da" | "en") =>
  new Intl.DateTimeFormat(locale === "da" ? "da-DK" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Copenhagen"
  }).format(new Date(value));

const formatAge = (minutes: number, locale: "da" | "en") => {
  if (minutes < 1) return locale === "da" ? "nu" : "now";
  return locale === "da" ? `${minutes} min siden` : `${minutes} min ago`;
};

export default function App() {
  const state = useWeatherStore();
  const [now, setNow] = useState(() => Date.now());
  const forecastLatitude = Number(state.selectedLocation.latitude.toFixed(2));
  const forecastLongitude = Number(state.selectedLocation.longitude.toFixed(2));
  const manifest = useQuery({
    queryKey: ["radar-frames"],
    queryFn: ({ signal }) => getRadarManifest(signal),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true
  });
  const forecast = useQuery({
    queryKey: ["forecast", forecastLatitude, forecastLongitude],
    queryFn: ({ signal }) => getForecast(forecastLatitude, forecastLongitude, signal),
    staleTime: 10 * 60_000,
    gcTime: 6 * 60 * 60_000,
    retry: 3,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4_000),
    refetchInterval: 10 * 60_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
    placeholderData: keepPreviousData
  });
  const frames = manifest.data?.frames ?? [];
  const lastFrameIndex = Math.max(frames.length - 1, 0);
  const safeIndex = state.selectedFrame < 0
    ? lastFrameIndex
    : Math.min(state.selectedFrame, lastFrameIndex);
  const activeFrame = frames[safeIndex];
  const latestFrame = frames[lastFrameIndex];
  const t = (key: Parameters<typeof translate>[1]) => translate(state.locale, key);
  const ageMinutes = latestFrame
    ? Math.max(0, Math.floor((now - new Date(latestFrame.observedAt).getTime()) / 60_000))
    : Infinity;
  const isStale = ageMinutes > radarDelayBudgetMinutes;
  const currentHour = new Date(now);
  currentHour.setMinutes(0, 0, 0);
  const forecastPoints = (forecast.data?.points ?? [])
    .filter((point) => new Date(point.step).getTime() >= currentHour.getTime())
    .slice(0, 4);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!state.playing || frames.length < 2) return;
    if (safeIndex >= lastFrameIndex) {
      state.setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => state.setSelectedFrame(safeIndex + 1), 700);
    return () => window.clearTimeout(timer);
  }, [frames.length, lastFrameIndex, safeIndex, state]);

  useEffect(() => {
    if (frames.length && (state.selectedFrame < 0 || state.selectedFrame >= frames.length)) {
      state.setSelectedFrame(frames.length - 1);
    }
  }, [frames.length, state]);

  const togglePlayback = () => {
    if (state.playing) {
      state.setPlaying(false);
      return;
    }
    if (safeIndex >= lastFrameIndex) state.setSelectedFrame(0);
    state.setPlaying(true);
  };

  return (
    <main className="app-shell">
      <a className="skip-link" href="#weather-panel">{t("skipToWeather")}</a>
      <Suspense fallback={<div className="map-loading" role="status">{t("loadingMap")}</div>}>
        <WeatherMap frames={frames} activeIndex={safeIndex} />
      </Suspense>

      <header className="topbar glass" aria-label="WetMap">
        <div className="brand-mark" aria-hidden="true"><CloudRain size={19} /></div>
        <div>
          <strong>wetmap</strong>
          <span>{forecastLatitude.toFixed(2)}°n · {forecastLongitude.toFixed(2)}°e</span>
        </div>
        <span className={`freshness ${isStale ? "is-stale" : ""}`} role="status" title={t("freshnessHelp")}>
          <Radio size={13} aria-hidden="true" />
          {isStale ? t("stale") : t("fresh")} · {Number.isFinite(ageMinutes) ? formatAge(ageMinutes, state.locale) : "–"}
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

      <section id="weather-panel" className="weather-card glass" aria-labelledby="forecast-title">
        <div className="eyebrow">
          <Wind size={15} aria-hidden="true" /> DMI HARMONIE
          {forecast.isFetching && !forecast.isLoading && <span role="status"> · {t("updatingForecast")}</span>}
        </div>
        <h2 id="forecast-title">{t("forecast")}</h2>
        {forecast.isLoading && <p className="muted" role="status">{t("loadingForecast")}</p>}
        {forecast.isError && <p className="muted">{t("forecastUnavailable")}</p>}
        {!forecast.isLoading && !forecast.isError && forecastPoints.length === 0 && (
          <p className="muted">{t("forecastUnavailable")}</p>
        )}
        {forecastPoints.map((point) => (
          <div className="forecast-row" key={point.step}>
            <time dateTime={point.step}>
              {new Date(point.step).getTime() < currentHour.getTime() + 3_600_000 ? t("now") : formatTime(point.step, state.locale)}
            </time>
            <strong>{point.temperatureC == null ? "–" : `${Math.round(point.temperatureC)}°`}</strong>
            <span>{point.windSpeedMs == null ? "–" : `${point.windSpeedMs.toFixed(1)} m/s`}</span>
          </div>
        ))}
      </section>

      <aside className="legend glass" aria-label={t("reflectivity")}>
        <strong>{t("reflectivity")}</strong>
        <div className="legend-scale" aria-hidden="true">
          {RADAR_SCALE.map((entry) => <span key={entry.min} style={{ backgroundColor: entry.color }} />)}
        </div>
        <div className="legend-labels"><span>−10</span><span>20</span><span>50+</span></div>
      </aside>

      <section className="timeline glass" aria-labelledby="timeline-title">
        <div className="timeline-heading">
          <div>
            <span className="eyebrow">{safeIndex === lastFrameIndex ? t("latestObservation") : t("observed")}</span>
            <h1 id="timeline-title">{activeFrame ? formatTime(activeFrame.observedAt, state.locale) : t("radar")}</h1>
          </div>
          <div className="timeline-actions">
            <div className="live-clock">
              <span>{t("now")}</span>
              <time dateTime={new Date(now).toISOString()}>{formatTime(now, state.locale)}</time>
            </div>
            <button
              className="play-button"
              onClick={togglePlayback}
              aria-label={state.playing ? t("pause") : t("play")}
              disabled={frames.length < 2}
            >
              {state.playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
            </button>
          </div>
        </div>

        {frames.length ? (
          <>
            <input
              className="scrubber"
              type="range"
              min="0"
              max={Math.max(frames.length - 1, 0)}
              value={safeIndex}
              onChange={(event) => state.setSelectedFrame(Number(event.target.value))}
              aria-label={t("radarTime")}
              aria-valuetext={activeFrame ? formatTime(activeFrame.observedAt, state.locale) : undefined}
            />
            <div className="timeline-ticks">
              <time dateTime={frames[0].observedAt}>{formatTime(frames[0].observedAt, state.locale)}</time>
              <span>{t("observedHistory")}</span>
              <time dateTime={latestFrame.observedAt}>{formatTime(latestFrame.observedAt, state.locale)}</time>
            </div>
            <p className="timeline-note">{t("futureRadarNote")}</p>
          </>
        ) : (
          <div className="empty-state" role="status"><strong>{t("noData")}</strong><span>{t("noDataDetail")}</span></div>
        )}

        <div className="control-grid">
          <label>
            <span>{t("opacity")} <output>{Math.round(state.opacity * 100)}%</output></span>
            <input type="range" min="0.1" max="1" step="0.05" value={state.opacity} onChange={(e) => state.setOpacity(Number(e.target.value))} />
          </label>
          <button
            className={`mode-button ${state.precise2d ? "is-active" : ""}`}
            onClick={() => state.setPrecise2d(!state.precise2d)}
            aria-pressed={state.precise2d}
          >
            <Layers3 size={17} aria-hidden="true" /> {state.precise2d ? t("precise") : t("buildings")}
          </button>
        </div>
      </section>

      <footer className="attribution">
        <a href="https://www.dmi.dk/friedata" target="_blank" rel="noreferrer">{DMI_ATTRIBUTION}</a>
        {forecast.data?.source === "open-meteo-dmi" && <span> · <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a></span>}
        {activeFrame && <span> · {t("fetched")} <time dateTime={activeFrame.fetchedAt}>{formatTime(activeFrame.fetchedAt, state.locale)}</time></span>}
        <span> · © OpenStreetMap · OpenFreeMap</span>
      </footer>
    </main>
  );
}
