// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { useWeatherStore } from "./store";

const apiMocks = vi.hoisted(() => ({
  manifest: {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
    frames: [] as Array<Record<string, unknown>>,
  },
  forecast: {
    latitude: 56.16,
    longitude: 10.2,
    fetchedAt: new Date().toISOString(),
    attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
    points: [] as Array<Record<string, unknown>>,
  },
  rain: {
    latitude: 56.16,
    longitude: 10.2,
    fetchedAt: "2026-10-11T08:00:00Z",
    attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
    source: "open-meteo-dmi",
    model: "DMI HARMONIE AROME",
    displayResolutionMinutes: 15,
    sourceResolutionMinutes: 60,
    isInterpolated: true,
    points: [] as Array<Record<string, unknown>>,
  },
  locations: [] as Array<{
    id: string;
    name: string;
    context: string;
    latitude: number;
    longitude: number;
    type: "address" | "place";
  }>,
}));

vi.mock("./components/WeatherMap", () => ({
  default: ({
    frames,
    activeIndex,
  }: {
    frames: Array<{ id: string }>;
    activeIndex: number;
  }) => (
    <div aria-label="test map" data-testid="active-frame">
      {frames[activeIndex]?.id}
    </div>
  ),
}));
vi.mock("./api", () => ({
  getRadarManifest: async () => apiMocks.manifest,
  getForecast: async () => apiMocks.forecast,
  getRainNextHour: async () => apiMocks.rain,
  searchLocations: async (query: string) => ({
    query,
    results: apiMocks.locations,
  }),
  reverseLocation: async (latitude: number, longitude: number) => ({
    id: "device-location",
    name: "Min placering",
    context: "Aarhus",
    latitude,
    longitude,
    type: "place",
  }),
}));

beforeEach(() => {
  window.localStorage.clear();
  apiMocks.manifest.frames = [];
  apiMocks.forecast.points = [];
  apiMocks.rain.points = [];
  apiMocks.locations = [];
  useWeatherStore.setState({
    selectedFrame: -1,
    playing: false,
    locale: "da",
    selectedLocation: {
      id: "aarhus",
      name: "Aarhus",
      context: "Region Midtjylland",
      latitude: 56.1629,
      longitude: 10.2039,
    },
    favoriteLocations: [],
  });
});

afterEach(cleanup);

it("shows an honest empty radar state", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("Venter på radardata")).toBeInTheDocument();
  expect(screen.getByText(/Baseret på data fra DMI/)).toBeInTheDocument();
});

it("opens on the latest available radar observation", async () => {
  const base = {
    fetchedAt: "2026-10-10T21:01:00Z",
    url: "/frames/frame.webp",
    bounds: [7, 54, 13, 58],
    product: "DBZH",
    unit: "dBZ",
    sha256: "test",
  };
  apiMocks.manifest.frames = [
    { ...base, id: "older", observedAt: "2026-10-10T20:55:00Z" },
    { ...base, id: "latest", observedAt: "2026-10-10T21:00:00Z" },
  ];
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );

  await waitFor(() =>
    expect(screen.getByTestId("active-frame")).toHaveTextContent("latest"),
  );
  expect(screen.getByRole("slider", { name: "Radar-tidspunkt" })).toHaveValue(
    "1",
  );
  expect(screen.getByText("Seneste observation")).toBeInTheDocument();

  fireEvent.change(screen.getByRole("slider", { name: "Radar-tidspunkt" }), {
    target: { value: "0" },
  });
  await waitFor(() =>
    expect(screen.getByTestId("active-frame")).toHaveTextContent("older"),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Gå til seneste observation" }),
  );
  await waitFor(() =>
    expect(screen.getByTestId("active-frame")).toHaveTextContent("latest"),
  );
});

it("minimizes the latest observation panel and remembers the preference", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  const minimize = await screen.findByRole("button", {
    name: "Minimer seneste observation",
  });

  fireEvent.click(minimize);

  expect(screen.queryByText("Radar-gennemsigtighed")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Vis seneste observation" }),
  ).toHaveAttribute("aria-expanded", "false");
  expect(window.localStorage.getItem("wetmap:timeline-collapsed")).toBe("true");

  view.unmount();
  const nextClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={nextClient}>
      <App />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("button", { name: "Vis seneste observation" }),
  ).toBeInTheDocument();
});

it("searches for a place, moves the forecast location, and saves a favorite", async () => {
  apiMocks.locations = [
    {
      id: "photon:N:1",
      name: "København",
      context: "Region Hovedstaden",
      latitude: 55.6761,
      longitude: 12.5683,
      type: "place",
    },
  ];
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );

  const input = await screen.findByRole("searchbox", {
    name: "Søg efter by eller adresse",
  });
  fireEvent.change(input, { target: { value: "København" } });
  const resultLabel = await screen.findByText(
    "København",
    {},
    { timeout: 2_000 },
  );
  fireEvent.click(resultLabel.closest("button")!);

  await waitFor(() =>
    expect(useWeatherStore.getState().selectedLocation.name).toBe("København"),
  );
  expect(input).toHaveValue("København");

  fireEvent.click(screen.getByRole("button", { name: "Gem sted som favorit" }));
  expect(useWeatherStore.getState().favoriteLocations).toHaveLength(1);
  expect(window.localStorage.getItem("wetmap:favorite-locations")).toContain(
    "København",
  );

  fireEvent.click(screen.getByRole("button", { name: "Find min placering" }));
  expect(
    screen.getByText("Din browser understøtter ikke placering."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Skift sprog" }));
  expect(
    screen.getByText("Your browser does not support location services."),
  ).toBeInTheDocument();
});

it("explains the next-hour rain estimate and handles blocked alerts", async () => {
  apiMocks.rain.points = [
    {
      startsAt: "2026-10-11T08:15:00Z",
      endsAt: "2026-10-11T08:30:00Z",
      precipitationMm: 0,
      intensity: "none",
    },
    {
      startsAt: "2026-10-11T08:30:00Z",
      endsAt: "2026-10-11T08:45:00Z",
      precipitationMm: 0.2,
      intensity: "light",
    },
    {
      startsAt: "2026-10-11T08:45:00Z",
      endsAt: "2026-10-11T09:00:00Z",
      precipitationMm: 0.4,
      intensity: "light",
    },
    {
      startsAt: "2026-10-11T09:00:00Z",
      endsAt: "2026-10-11T09:15:00Z",
      precipitationMm: 0.3,
      intensity: "light",
    },
  ];
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("Regn starter ca. 10.30")).toBeInTheDocument();
  expect(screen.getByText("Forventet 0.90 mm")).toBeInTheDocument();
  expect(screen.getByText(/interpoleret fra DMI/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Varsl mig" }));
  expect(
    screen.getByText("Notifikationer er blokeret i browseren."),
  ).toBeInTheDocument();
});
