import { useState } from "react";
import { translate } from "../i18n";

interface Props {
  kind: "point" | "rain";
  locale: "da" | "en";
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  isEmpty: boolean;
  onRetry: () => Promise<unknown>;
}

export default function ForecastRecovery({
  kind,
  locale,
  isLoading,
  isFetching,
  isError,
  isEmpty,
  onRetry,
}: Props) {
  const [retrying, setRetrying] = useState(false);
  const unavailable = isError || (!isLoading && isEmpty);
  const loading = isLoading || (isFetching && (retrying || unavailable));
  const showRetry = unavailable || retrying;
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  const message = loading
    ? t("loadingForecast")
    : isError
      ? t(kind === "rain" ? "rainUnavailable" : "forecastUnavailable")
      : isEmpty
        ? t(kind === "rain" ? "rainEmpty" : "forecastEmpty")
        : undefined;

  async function retry() {
    if (isFetching || retrying) return;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="forecast-recovery">
      <p className="muted" role="status">
        {message}
      </p>
      {showRetry && (
        <div className="forecast-recovery-actions">
          <p className="muted">{t("forecastAutoRefresh")}</p>
          <button
            type="button"
            className="forecast-retry"
            disabled={isFetching || retrying}
            onClick={() => void retry()}
          >
            {t(kind === "rain" ? "retryRainForecast" : "retryPointForecast")}
          </button>
        </div>
      )}
    </div>
  );
}
