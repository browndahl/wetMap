import { create } from "zustand";

type Locale = "da" | "en";

interface WeatherState {
  locale: Locale;
  opacity: number;
  selectedFrame: number;
  playing: boolean;
  precise2d: boolean;
  selectedLocation: { latitude: number; longitude: number };
  setLocale: (locale: Locale) => void;
  setOpacity: (opacity: number) => void;
  setSelectedFrame: (frame: number) => void;
  setPlaying: (playing: boolean) => void;
  setPrecise2d: (precise2d: boolean) => void;
  setSelectedLocation: (location: { latitude: number; longitude: number }) => void;
}

export const useWeatherStore = create<WeatherState>((set) => ({
  locale: "da",
  opacity: 0.7,
  selectedFrame: 0,
  playing: false,
  precise2d: false,
  selectedLocation: { latitude: 56.1629, longitude: 10.2039 },
  setLocale: (locale) => set({ locale }),
  setOpacity: (opacity) => set({ opacity }),
  setSelectedFrame: (selectedFrame) => set({ selectedFrame }),
  setPlaying: (playing) => set({ playing }),
  setPrecise2d: (precise2d) => set({ precise2d }),
  setSelectedLocation: (selectedLocation) => set({ selectedLocation })
}));
