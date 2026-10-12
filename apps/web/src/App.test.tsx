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
  nowcast: {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
    method: "adaptive-optical-flow-persistence",
    basedOnObservedAt: "2026-10-10T21:00:00Z",
    sourceFrameCount: 3,
    frames: [] as Array<Record<string, unknown>>,
  },
  quality: {
    schemaVersion: 4,
    generatedAt: "2026-10-12T12:30:00Z",
    latestVerifiedAt: "2026-10-12T12:29:00Z",
    algorithmVersion: "adaptive-optical-flow-persistence-v1",
    thresholdDbz: 20,
    sampleCount: 48,
    totalSampleCount: 48,
    meanCriticalSuccessIndex: null,
    meanCriticalSuccessIndexSkill: null,
    observatory: {
      schemaVersion: 1,
      overallStatus: "awaiting-rain",
      targetHorizonMinutes: [15, 30, 45, 60],
      qualityGate: {
        minimumSamples: 12,
        minimumEventPixels: 100,
        minimumCriticalSuccessIndex: 0.2,
        minimumSkillOverPersistence: 0,
      },
      verifiedHorizonCount: 0,
      horizons: [15, 30, 45, 60].map((targetLeadMinutes) => ({
        targetLeadMinutes,
        windowStartMinutes: targetLeadMinutes - 5,
        windowEndMinutes: targetLeadMinutes === 60 ? 60 : targetLeadMinutes + 5,
        status: "awaiting-rain",
        meetsQualityGate: false,
        sampleCount: 12,
        eventPixelCount: 0,
        validPixels: 12_000,
        hits: 0,
        misses: 0,
        falseAlarms: 0,
        precision: null,
        recall: null,
        falseAlarmRate: null,
        missRate: null,
        criticalSuccessIndex: null,
        meanDbzMeanAbsoluteError: 0,
        meanCriticalSuccessIndexSkill: null,
        meanPersistenceCriticalSuccessIndex: null,
      })),
    },
    groundGauge: {
      observationCount: 12,
      stationComparisonCount: 1260,
      hits: 1,
      misses: 3,
      falseAlarms: 0,
      precision: 1,
      recall: 0.25,
      criticalSuccessIndex: 0.25,
    },
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
  getPushConfig: vi.fn(async () => ({
    available: true,
    publicKey: "test-key",
  })),
  savePushSubscription: vi.fn(async () => ({ subscribed: true })),
  deletePushSubscription: vi.fn(async () => undefined),
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
  getRadarNowcast: async () => apiMocks.nowcast,
  getPrecisionObservatory: async () => apiMocks.quality,
  getForecast: async () => apiMocks.forecast,
  getRainNextHour: async () => apiMocks.rain,
  getPushConfig: apiMocks.getPushConfig,
  savePushSubscription: apiMocks.savePushSubscription,
  deletePushSubscription: apiMocks.deletePushSubscription,
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
  apiMocks.nowcast.frames = [];
  apiMocks.forecast.points = [];
  apiMocks.rain.points = [];
  apiMocks.rain.source = "open-meteo-dmi";
  apiMocks.locations = [];
  apiMocks.getPushConfig.mockClear();
  apiMocks.savePushSubscription.mockClear();
  apiMocks.deletePushSubscription.mockClear();
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

it("labels future optical-flow frames as nowcasts with confidence", async () => {
  const observedAt = new Date(Date.now() - 5 * 60_000).toISOString();
  const predictedAt = new Date(Date.now() + 5 * 60_000).toISOString();
  apiMocks.manifest.frames = [
    {
      id: "latest",
      observedAt,
      fetchedAt: new Date().toISOString(),
      url: "/frames/latest.webp",
      bounds: [7, 54, 13, 58],
      product: "DBZH",
      unit: "dBZ",
      sha256: "observed",
    },
  ];
  apiMocks.nowcast.basedOnObservedAt = observedAt;
  apiMocks.nowcast.frames = [
    {
      id: "latest-plus-05m",
      predictedAt,
      generatedAt: new Date().toISOString(),
      basedOnObservedAt: observedAt,
      leadMinutes: 5,
      url: "/nowcast/latest-plus-05m.webp",
      bounds: [7, 54, 13, 58],
      product: "DBZH_NOWCAST",
      unit: "dBZ",
      confidence: 0.88,
      forecastMethod: "optical-flow",
      sha256: "predicted",
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

  await waitFor(
    () =>
      expect(screen.getByTestId("active-frame")).toHaveTextContent(
        "latest-plus-05m",
      ),
    { timeout: 1_500 },
  );
  expect(screen.getByText("Radar-nowcast · +5 min")).toBeInTheDocument();
  expect(
    screen.getByText("Estimeret sikkerhed 88% · Optisk flow"),
  ).toBeInTheDocument();
  expect(screen.getByText(/optisk flow/)).toBeInTheDocument();
});

it("opens the precision observatory with honest dry-weather status", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );

  fireEvent.click(
    await screen.findByRole("button", { name: "Åbn Precision Observatory" }),
  );

  expect(
    screen.getByRole("heading", { name: "Precision Observatory" }),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Afventer regnhændelser")).toHaveLength(5);
  expect(screen.getByText("+15 min")).toBeInTheDocument();
  expect(screen.getAllByText("Falske varsler")).toHaveLength(4);
  expect(screen.getByText("1.260 stationssammenligninger")).toBeInTheDocument();
  expect(screen.getByText("Målt regn fanget")).toBeInTheDocument();
  expect(screen.getByText("25%")).toBeInTheDocument();
  expect(screen.getByText("Målt regn overset")).toBeInTheDocument();
  expect(screen.getByText("75%")).toBeInTheDocument();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(window.navigator, "serviceWorker");
});

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

it("automatically plays recent radar history and finishes on the latest observation", async () => {
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

  await waitFor(() => {
    expect(screen.getByTestId("active-frame")).toHaveTextContent("older");
    expect(
      screen.getByRole("button", { name: "Sæt radar på pause" }),
    ).toBeInTheDocument();
  });
  await waitFor(
    () =>
      expect(screen.getByTestId("active-frame")).toHaveTextContent("latest"),
    { timeout: 1_500 },
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

  expect(
    await screen.findByText("Regn forventes 10.30–10.45"),
  ).toBeInTheDocument();
  expect(screen.getByText("Forventet 0.90 mm")).toBeInTheDocument();
  expect(screen.getByText("Sikkerhed ikke opgjort")).toBeInTheDocument();
  expect(screen.getByText("HARMONIE-model")).toBeInTheDocument();
  expect(screen.getByText("45 min regn")).toBeInTheDocument();
  expect(screen.getByText(/interpoleret fra DMI/)).toBeInTheDocument();
  expect(screen.getAllByText("Let")).toHaveLength(4);
  expect(
    screen.getByText((_, element) => element?.textContent === "0,20 mm"),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Varsl mig" }));
  expect(
    screen.getByText(/Baggrundsvarsler kunne ikke aktiveres/),
  ).toBeInTheDocument();
});

it("labels radar-backed intervals and weak echoes without claiming ground rain", async () => {
  apiMocks.rain.source = "dmi-radar-nowcast-harmonie";
  apiMocks.rain.points = [
    {
      startsAt: "2026-10-11T08:15:00Z",
      endsAt: "2026-10-11T08:30:00Z",
      precipitationMm: 0.01,
      intensity: "trace",
      source: "radar-nowcast",
      reflectivityDbz: 14,
      confidence: 0.94,
      forecastMethod: "persistence",
    },
    {
      startsAt: "2026-10-11T08:30:00Z",
      endsAt: "2026-10-11T08:45:00Z",
      precipitationMm: 0,
      intensity: "none",
      source: "harmonie",
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

  expect(await screen.findByText("Radar + model")).toBeInTheDocument();
  expect(screen.getByText("Radar · 14")).toBeInTheDocument();
  expect(
    screen.getByTitle("Radar · 14 dBZ · Stabilitetsmodel"),
  ).toBeInTheDocument();
  expect(screen.getByText("Model")).toBeInTheDocument();
  expect(
    screen.getByText("Svagt radarekko · regn ved jorden er usikkert"),
  ).toBeInTheDocument();
  expect(screen.getByText("Høj sikkerhed · 94%")).toBeInTheDocument();
  expect(screen.getByText("Radar-nowcast")).toBeInTheDocument();
  expect(
    screen.getByText(/Nærmeste intervaller følger DMI-radar/),
  ).toBeInTheDocument();
});

it("creates a server-backed push subscription from a user gesture", async () => {
  const subscription = {
    endpoint: "https://push.example/subscription",
    toJSON: () => ({
      endpoint: "https://push.example/subscription",
      keys: { auth: "auth", p256dh: "key" },
    }),
    unsubscribe: vi.fn(async () => true),
  };
  const pushManager = {
    getSubscription: vi.fn(async () => null),
    subscribe: vi.fn(async () => subscription),
  };
  Object.defineProperty(window.navigator, "serviceWorker", {
    configurable: true,
    value: { ready: Promise.resolve({ pushManager }) },
  });
  vi.stubGlobal("PushManager", class {});
  vi.stubGlobal("Notification", { permission: "granted" });
  apiMocks.rain.points = [
    {
      startsAt: "2026-10-11T08:15:00Z",
      endsAt: "2026-10-11T08:30:00Z",
      precipitationMm: 0.1,
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

  fireEvent.click(await screen.findByRole("button", { name: "Varsl mig" }));

  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Regnvarsel slået til" }),
    ).toBeInTheDocument(),
  );
  expect(pushManager.subscribe).toHaveBeenCalledWith(
    expect.objectContaining({ userVisibleOnly: true }),
  );
  expect(apiMocks.savePushSubscription).toHaveBeenCalledWith(
    subscription,
    56.1629,
    10.2039,
    "Aarhus",
    "da",
  );
  expect(
    screen.getByText("Virker også, når WetMap er lukket."),
  ).toBeInTheDocument();
});
