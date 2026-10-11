import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LoaderCircle, LocateFixed, MapPin, Search, Star } from "lucide-react";
import type { LocationResult } from "@wetmap/shared";
import { reverseLocation, searchLocations } from "../api";
import { translate } from "../i18n";
import { type SelectedLocation, useWeatherStore } from "../store";

const toSelectedLocation = (location: LocationResult): SelectedLocation => ({
  id: location.id,
  name: location.name,
  context: location.context,
  latitude: location.latitude,
  longitude: location.longitude,
});

export default function LocationSearch() {
  const locale = useWeatherStore((state) => state.locale);
  const selectedLocation = useWeatherStore((state) => state.selectedLocation);
  const favoriteLocations = useWeatherStore((state) => state.favoriteLocations);
  const setSelectedLocation = useWeatherStore(
    (state) => state.setSelectedLocation,
  );
  const toggleFavoriteLocation = useWeatherStore(
    (state) => state.toggleFavoriteLocation,
  );
  const [input, setInput] = useState(selectedLocation.name);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);

  useEffect(() => setInput(selectedLocation.name), [selectedLocation]);

  useEffect(() => {
    const query = input.trim();
    if (query.length < 2 || query === selectedLocation.name) {
      setDebouncedQuery("");
      return;
    }
    const timer = window.setTimeout(() => setDebouncedQuery(query), 350);
    return () => window.clearTimeout(timer);
  }, [input, selectedLocation.name]);

  const locations = useQuery({
    queryKey: [
      "location-search",
      debouncedQuery,
      selectedLocation.latitude.toFixed(1),
      selectedLocation.longitude.toFixed(1),
    ],
    queryFn: ({ signal }) =>
      searchLocations(
        debouncedQuery,
        selectedLocation.latitude,
        selectedLocation.longitude,
        signal,
      ),
    enabled: debouncedQuery.length >= 2,
    staleTime: 24 * 60 * 60_000,
    retry: 1,
  });
  const results = locations.data?.results ?? [];
  const isFavorite = useMemo(
    () =>
      favoriteLocations.some((favorite) => favorite.id === selectedLocation.id),
    [favoriteLocations, selectedLocation.id],
  );

  const selectLocation = (location: SelectedLocation) => {
    setSelectedLocation(location);
    setInput(location.name);
    setDebouncedQuery("");
    setLocationError(null);
    setOpen(false);
  };

  const locateUser = () => {
    if (!("geolocation" in navigator)) {
      setLocationError(t("locationUnavailable"));
      return;
    }
    setLocating(true);
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const fallback: SelectedLocation = {
          id: `device:${coords.latitude.toFixed(5)},${coords.longitude.toFixed(5)}`,
          name: t("myLocation"),
          context: `${coords.latitude.toFixed(3)}°N · ${coords.longitude.toFixed(3)}°E`,
          latitude: coords.latitude,
          longitude: coords.longitude,
        };
        try {
          const resolved = await reverseLocation(
            coords.latitude,
            coords.longitude,
          );
          selectLocation(toSelectedLocation(resolved));
        } catch {
          selectLocation(fallback);
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocating(false);
        setLocationError(t("locationDenied"));
      },
      { enableHighAccuracy: false, timeout: 8_000, maximumAge: 5 * 60_000 },
    );
  };

  return (
    <section
      className="location-search glass"
      aria-label={t("locationSearch")}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <form
        className="location-search-form"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (results[0]) selectLocation(toSelectedLocation(results[0]));
          else setOpen(true);
        }}
      >
        <Search size={17} aria-hidden="true" />
        <label className="sr-only" htmlFor="location-query">
          {t("locationSearch")}
        </label>
        <input
          id="location-query"
          type="search"
          value={input}
          placeholder={t("locationPlaceholder")}
          autoComplete="off"
          spellCheck="false"
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setInput(event.target.value);
            setOpen(true);
            setLocationError(null);
          }}
          aria-expanded={open}
          aria-controls="location-results"
        />
        {locations.isFetching && (
          <LoaderCircle
            className="is-spinning"
            size={16}
            aria-label={t("searching")}
          />
        )}
        <button
          type="button"
          className="location-action"
          onClick={locateUser}
          aria-label={t("locate")}
          title={t("locate")}
          disabled={locating}
        >
          {locating ? (
            <LoaderCircle className="is-spinning" aria-hidden="true" />
          ) : (
            <LocateFixed aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          className={`location-action favorite-toggle ${isFavorite ? "is-active" : ""}`}
          onClick={() => toggleFavoriteLocation(selectedLocation)}
          aria-label={isFavorite ? t("removeFavorite") : t("addFavorite")}
          aria-pressed={isFavorite}
          title={isFavorite ? t("removeFavorite") : t("addFavorite")}
        >
          <Star
            aria-hidden="true"
            fill={isFavorite ? "currentColor" : "none"}
          />
        </button>
      </form>

      {open && (
        <div id="location-results" className="location-results">
          {locations.isError && (
            <p className="location-message" role="alert">
              {t("searchUnavailable")}
            </p>
          )}
          {!locations.isError &&
            debouncedQuery.length >= 2 &&
            !locations.isFetching &&
            results.length === 0 && (
              <p className="location-message">{t("noLocations")}</p>
            )}
          {results.map((result) => (
            <button
              type="button"
              className="location-result"
              key={result.id}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectLocation(toSelectedLocation(result))}
            >
              <MapPin size={16} aria-hidden="true" />
              <span>
                <strong>{result.name}</strong>
                <small>{result.context}</small>
              </span>
            </button>
          ))}
          {debouncedQuery.length < 2 && favoriteLocations.length > 0 && (
            <div className="favorite-locations">
              <span>{t("favorites")}</span>
              {favoriteLocations.map((favorite) => (
                <button
                  type="button"
                  key={favorite.id}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => selectLocation(favorite)}
                >
                  <Star size={13} fill="currentColor" aria-hidden="true" />
                  {favorite.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {locationError && (
        <p className="location-error" role="alert">
          {locationError}
        </p>
      )}
    </section>
  );
}
