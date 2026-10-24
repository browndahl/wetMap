// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { needsIphoneInstallation } from "./platform";

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "maxTouchPoints");
  Reflect.deleteProperty(navigator, "standalone");
});

it("requires home-screen installation in an ordinary iPhone browser", () => {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
  );
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
  expect(needsIphoneInstallation()).toBe(true);
});

it("allows the installed iPhone app through the standard display-mode signal", () => {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (iPhone)",
  );
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });
  expect(needsIphoneInstallation()).toBe(false);
});

it("recognizes iPad desktop mode and does not flag desktop or Android", () => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Macintosh)",
  );
  Object.defineProperty(navigator, "maxTouchPoints", {
    configurable: true,
    value: 5,
  });
  expect(needsIphoneInstallation()).toBe(true);
  Object.defineProperty(navigator, "maxTouchPoints", {
    configurable: true,
    value: 0,
  });
  expect(needsIphoneInstallation()).toBe(false);
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Linux; Android 15)",
  );
  Object.defineProperty(navigator, "maxTouchPoints", {
    configurable: true,
    value: 5,
  });
  expect(needsIphoneInstallation()).toBe(false);
});

it("recognizes Safari's standalone flag without display-mode support", () => {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (iPhone)",
  );
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
  Object.defineProperty(navigator, "standalone", {
    value: true,
    configurable: true,
  });
  expect(needsIphoneInstallation()).toBe(false);
});
