import { lazy, Suspense, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { CloudRain, Languages, Layers3, Pause, Play, Radio, Wind } from "lucide-react";
import { DMI_ATTRIBUTION, RADAR_SCALE } from "@wetmap/shared";
import { getForecast, getRadarManifest } from "./api";
import { translate } from "./i18n";
import { useWeatherStore } from "./store";

const WeatherMap = lazy(() => import("./components/WeatherMap"));

const formatTime = (value: string, locale: "da" | "en") =>
  new Intl.DateTimeFormat(locale === "da" ? "da-DK" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Copenhagen"
  }).format(new Date(value));

export default function App() {
  const state = useWeatherStore();
  const manifest = useQuery({ queryKey: ["radar-frames"], queryFn: ({ signal }) => getRadarManifest(signal), refetchInterval: 60_000 });
  const forecast = useQuery({
    queryKey: ["forecast", state.selectedLocation],
    queryFn: ({ signal }) => getForecast(state.selectedLocation.latitude, state.selectedLocation.longitude, signal),
    staleTime: 10 * 60_000
  });
  const frames = manifest.data?.frames ?? [];
  const safeIndex = Math.min(state.selectedFrame, Math.max(frames.length - 1, 0));
  const activeFrame = frames[safeIndex];
  const t = (key: Parameters<typeof translate>[1]) => translate(state.locale, key);
  const ageMinutes = activeFrame
    ? (manifest.dataUpdatedAt - new Date(activeFrame.observedAt).getTime()) / 60_000
    : Infinity;

  useEffect(() => {
    if (!state.playing || frames.length < 2) return;
    const timer = window.setInterval(() => {
      state.setSelectedFrame((safeIndex + 1) % frames.length);
    }, 900);
    return () => window.clearInterval(timer);
  }, [frames.length, safeIndex, state]);

  useEffect(() => {
    if (frames.length && state.selectedFrame >= frames.length) state.setSelectedFrame(frames.length - 1);
  }, [frames.length, state]);

  return (
    <main className="app-shell">
      <a className="skip-link" href="#weather-panel">Spring til vejrinformation</a>
      <Suspense fallback={<div className="map-loading" role="status">Indlæser kort…</div>}>
        <WeatherMap frames={frames} activeIndex={safeIndex} />
      </Suspense>

      <header className="topbar glass" aria-label="WetMap">
        <div className="brand-mark" aria-hidden="true"><CloudRain size={19} /></div>
        <div>
          <strong>wetmap</strong>
          <span>aarhus · 56.16°n</span>
        </div>
        <span className={`freshness ${ageMinutes > 15 ? "is-stale" : ""}`}>
          <Radio size={13} aria-hidden="true" />
          {ageMinutes > 15 ? t("stale") : t("fresh")}
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
        <div className="eyebrow"><Wind size={15} aria-hidden="true" /> DMI HARMONIE</div>
        <h2 id="forecast-title">{t("forecast")}</h2>
        {forecast.isLoading && <p className="muted" role="status">Henter prognose…</p>}
        {forecast.isError && <p className="muted">Prognosen er midlertidigt utilgængelig.</p>}
        {forecast.data?.points.slice(0, 4).map((point) => (
          <div className="forecast-row" key={point.step}>
            <time dateTime={point.step}>{formatTime(point.step, state.locale)}</time>
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
            <span className="eyebrow">{t("observed")}</span>
            <h1 id="timeline-title">{activeFrame ? formatTime(activeFrame.observedAt, state.locale) : t("radar")}</h1>
          </div>
          <button
            className="play-button"
            onClick={() => state.setPlaying(!state.playing)}
            aria-label={state.playing ? t("pause") : t("play")}
            disabled={frames.length < 2}
          >
            {state.playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          </button>
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
              aria-label="Radar-tidspunkt"
            />
            <div className="timeline-ticks">
              <span>−60 min</span>
              <span>{t("now")}</span>
            </div>
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
        {activeFrame && <span> · hentet <time dateTime={activeFrame.fetchedAt}>{formatTime(activeFrame.fetchedAt, state.locale)}</time></span>}
        <span> · © OpenStreetMap · OpenFreeMap</span>
      </footer>
    </main>
  );
}
