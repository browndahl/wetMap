import { create } from "zustand";

type Locale = "da" | "en";

export interface SelectedLocation {
  id: string;
  name: string;
  context: string;
  latitude: number;
  longitude: number;
}

const defaultLocation: SelectedLocation = {
  id: "aarhus",
  name: "Aarhus",
  context: "Region Midtjylland",
  latitude: 56.1629,
  longitude: 10.2039,
};

const readFavorites = (): SelectedLocation[] => {
  try {
    const value = window.localStorage.getItem("wetmap:favorite-locations");
    if (!value) return [];
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is SelectedLocation =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as SelectedLocation).id === "string" &&
        typeof (item as SelectedLocation).name === "string" &&
        Number.isFinite((item as SelectedLocation).latitude) &&
        Number.isFinite((item as SelectedLocation).longitude),
    );
  } catch {
    return [];
  }
};

const writeFavorites = (favorites: SelectedLocation[]) => {
  try {
    window.localStorage.setItem(
      "wetmap:favorite-locations",
      JSON.stringify(favorites),
    );
  } catch {
    // Storage can be unavailable in hardened/private browser contexts.
  }
};

interface WeatherState {
  locale: Locale;
  opacity: number;
  selectedFrame: number;
  playing: boolean;
  precise2d: boolean;
  selectedLocation: SelectedLocation;
  favoriteLocations: SelectedLocation[];
  setLocale: (locale: Locale) => void;
  setOpacity: (opacity: number) => void;
  setSelectedFrame: (frame: number) => void;
  setPlaying: (playing: boolean) => void;
  setPrecise2d: (precise2d: boolean) => void;
  setSelectedLocation: (location: SelectedLocation) => void;
  toggleFavoriteLocation: (location: SelectedLocation) => void;
}

export const useWeatherStore = create<WeatherState>((set) => ({
  locale: "da",
  opacity: 0.7,
  selectedFrame: -1,
  playing: false,
  precise2d: false,
  selectedLocation: defaultLocation,
  favoriteLocations: readFavorites(),
  setLocale: (locale) => set({ locale }),
  setOpacity: (opacity) => set({ opacity }),
  setSelectedFrame: (selectedFrame) => set({ selectedFrame }),
  setPlaying: (playing) => set({ playing }),
  setPrecise2d: (precise2d) => set({ precise2d }),
  setSelectedLocation: (selectedLocation) => set({ selectedLocation }),
  toggleFavoriteLocation: (location) =>
    set((state) => {
      const exists = state.favoriteLocations.some(
        (favorite) => favorite.id === location.id,
      );
      const favoriteLocations = exists
        ? state.favoriteLocations.filter(
            (favorite) => favorite.id !== location.id,
          )
        : [location, ...state.favoriteLocations].slice(0, 5);
      writeFavorites(favoriteLocations);
      return { favoriteLocations };
    }),
}));
