// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
import { initialPrecise2d, useWeatherStore } from "./store";

beforeEach(() => {
  localStorage.clear();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
  Object.defineProperty(navigator, "deviceMemory", {
    value: undefined,
    configurable: true,
  });
});

it("uses 2D on small screens or low-memory devices", () => {
  expect(initialPrecise2d()).toBe(false);
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });
  expect(initialPrecise2d()).toBe(true);
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
  Object.defineProperty(navigator, "deviceMemory", {
    value: 4,
    configurable: true,
  });
  expect(initialPrecise2d()).toBe(true);
});

it("remembers an explicit 3D override on a phone", () => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });
  useWeatherStore.getState().setPrecise2d(false);
  expect(initialPrecise2d()).toBe(false);
  useWeatherStore.getState().setPrecise2d(true);
  expect(initialPrecise2d()).toBe(true);
});
