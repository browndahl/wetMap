// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./components/WeatherMap", () => ({ default: () => <div aria-label="test map" /> }));
vi.mock("./api", () => ({
  getRadarManifest: async () => ({ schemaVersion: 1, generatedAt: new Date().toISOString(), attribution: "Baseret på data fra DMI og efterfølgende bearbejdet", frames: [] }),
  getForecast: async () => ({ latitude: 56.16, longitude: 10.2, fetchedAt: new Date().toISOString(), attribution: "Baseret på data fra DMI og efterfølgende bearbejdet", points: [] })
}));

it("shows an honest empty radar state", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  expect(await screen.findByText("Venter på radardata")).toBeInTheDocument();
  expect(screen.getByText(/Baseret på data fra DMI/)).toBeInTheDocument();
});
