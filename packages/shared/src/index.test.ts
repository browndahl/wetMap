import { describe, expect, it } from "vitest";
import { DMI_ATTRIBUTION, RADAR_SCALE } from "./index";

describe("shared contracts", () => {
  it("keeps the legally required attribution exact", () => {
    expect(DMI_ATTRIBUTION).toBe("Baseret på data fra DMI og efterfølgende bearbejdet");
  });

  it("orders the reflectivity scale", () => {
    expect(RADAR_SCALE.every((entry, index, all) => index === 0 || entry.min > all[index - 1].min)).toBe(true);
  });
});
