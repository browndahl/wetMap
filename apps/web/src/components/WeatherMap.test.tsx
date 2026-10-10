// @vitest-environment jsdom
import { act, render } from "@testing-library/react";
import type { RadarFrame } from "@wetmap/shared";
import { beforeEach, expect, it, vi } from "vitest";
import WeatherMap from "./WeatherMap";

type MapHandler = () => void;

const map = vi.hoisted(() => {
  const state = {
    loadHandlers: [] as MapHandler[],
    pendingLoadHandler: undefined as MapHandler | undefined,
    isStyleLoaded: vi.fn(),
    addControl: vi.fn(),
    on: vi.fn((event: string, handler: MapHandler) => {
      if (event === "load") state.loadHandlers.push(handler);
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
    remove: vi.fn()
  };
  return state;
});

vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  Map: function Map() { return map; },
  NavigationControl: function NavigationControl() {},
  GeolocateControl: function GeolocateControl() {}
}));

const frame: RadarFrame = {
  id: "test-frame",
  observedAt: "2026-10-10T20:45:00Z",
  fetchedAt: "2026-10-10T20:46:00Z",
  url: "/frames/test-frame.webp",
  bounds: [7, 54, 13, 58],
  product: "DBZH",
  unit: "dBZ",
  sha256: "test"
};

beforeEach(() => {
  vi.clearAllMocks();
  map.loadHandlers.length = 0;
  map.pendingLoadHandler = undefined;
  map.isStyleLoaded.mockReturnValue(false);
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as typeof window.matchMedia;
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
    expect.objectContaining({ type: "image", url: expect.stringMatching(/\/frames\/test-frame\.webp$/) })
  );
  view.unmount();
});
