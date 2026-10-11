// @vitest-environment jsdom
import { act, render } from "@testing-library/react";
import type { RadarFrame } from "@wetmap/shared";
import { beforeEach, expect, it, vi } from "vitest";
import WeatherMap from "./WeatherMap";
import { useWeatherStore } from "../store";

type MapHandler = () => void;

const map = vi.hoisted(() => {
  const state = {
    loadHandlers: [] as MapHandler[],
    styleDataHandlers: [] as MapHandler[],
    pendingLoadHandler: undefined as MapHandler | undefined,
    isStyleLoaded: vi.fn(),
    addControl: vi.fn(),
    on: vi.fn((event: string, handler: MapHandler) => {
      if (event === "load") state.loadHandlers.push(handler);
      if (event === "styledata") state.styleDataHandlers.push(handler);
      return state;
    }),
    once: vi.fn((event: string, handler: MapHandler) => {
      if (event === "load") state.pendingLoadHandler = handler;
      return state;
    }),
    off: vi.fn(),
    getStyle: vi.fn(() => ({ layers: [] })),
    getLayer: vi.fn(),
    getSource: vi.fn(),
    addSource: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    removeSource: vi.fn(),
    setPaintProperty: vi.fn(),
    setLayoutProperty: vi.fn(),
    easeTo: vi.fn(),
    remove: vi.fn(),
  };
  return state;
});

vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  Map: function Map() {
    return map;
  },
  NavigationControl: function NavigationControl() {},
  GeolocateControl: function GeolocateControl() {},
}));

const frame: RadarFrame = {
  id: "test-frame",
  observedAt: "2026-10-10T20:45:00Z",
  fetchedAt: "2026-10-10T20:46:00Z",
  url: "/frames/test-frame.webp",
  bounds: [7, 54, 13, 58],
  product: "DBZH",
  unit: "dBZ",
  sha256: "test",
};

beforeEach(() => {
  vi.clearAllMocks();
  map.loadHandlers.length = 0;
  map.styleDataHandlers.length = 0;
  map.pendingLoadHandler = undefined;
  map.isStyleLoaded.mockReturnValue(false);
  map.getLayer.mockReturnValue(undefined);
  window.matchMedia = vi
    .fn()
    .mockReturnValue({ matches: false }) as typeof window.matchMedia;
  useWeatherStore.setState({ opacity: 0.7 });
});

it("renders a cached radar frame after the map style finishes loading", () => {
  const view = render(<WeatherMap frames={[frame]} activeIndex={0} />);

  expect(map.once).toHaveBeenCalledWith("load", expect.any(Function));
  expect(map.addSource).not.toHaveBeenCalledWith("radar-1", expect.anything());

  map.isStyleLoaded.mockReturnValue(true);
  act(() => {
    map.loadHandlers.forEach((handler) => handler());
    map.pendingLoadHandler?.();
  });

  expect(map.addSource).toHaveBeenCalledWith(
    "radar-1",
    expect.objectContaining({
      type: "image",
      url: expect.stringMatching(/\/frames\/test-frame\.webp$/),
    }),
  );
  view.unmount();
});

it("renders the first frame when style readiness arrives after the load event", () => {
  const view = render(<WeatherMap frames={[frame]} activeIndex={0} />);

  expect(map.on).toHaveBeenCalledWith("styledata", expect.any(Function));
  map.isStyleLoaded.mockReturnValue(true);
  act(() => {
    map.styleDataHandlers.forEach((handler) => handler());
  });

  expect(map.addSource).toHaveBeenCalledWith(
    "radar-1",
    expect.objectContaining({ type: "image" }),
  );
  view.unmount();
});

it("updates opacity without rebuilding the radar source", () => {
  map.isStyleLoaded.mockReturnValue(true);
  map.getLayer.mockImplementation((id: string) =>
    id === "radar-layer-1" ? {} : undefined,
  );
  const view = render(<WeatherMap frames={[frame]} activeIndex={0} />);
  const sourceAdds = map.addSource.mock.calls.length;

  act(() => useWeatherStore.getState().setOpacity(0.45));

  expect(map.addSource).toHaveBeenCalledTimes(sourceAdds);
  expect(map.setPaintProperty).toHaveBeenCalledWith(
    "radar-layer-1",
    "raster-opacity",
    0.45,
  );
  view.unmount();
});
