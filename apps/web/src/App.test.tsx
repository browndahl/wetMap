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
}));

beforeEach(() => {
  window.localStorage.clear();
  apiMocks.manifest.frames = [];
  apiMocks.forecast.points = [];
  useWeatherStore.setState({ selectedFrame: -1, playing: false, locale: "da" });
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
