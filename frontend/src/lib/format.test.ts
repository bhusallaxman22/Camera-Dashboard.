import { describe, expect, it } from "vitest";
import { toSearchParams } from "./api";
import {
  exposureLine,
  formatAperture,
  formatBytes,
  formatEv,
  formatRelative,
  formatShutter,
  titleCase,
} from "./format";

describe("format", () => {
  it("formats shutter speeds like a camera", () => {
    expect(formatShutter(1 / 500)).toBe("1/500");
    expect(formatShutter(1 / 8000)).toBe("1/8000");
    expect(formatShutter(2)).toBe('2"');
    expect(formatShutter(0.5)).toBe('0.5"');
    expect(formatShutter(null)).toBe("—");
  });

  it("formats exposure compensation in thirds", () => {
    expect(formatEv(0)).toBe("0 EV");
    expect(formatEv(1 / 3)).toBe("+1/3 EV");
    expect(formatEv(-1.6667)).toBe("−1 2/3 EV");
    expect(formatEv(2)).toBe("+2 EV");
  });

  it("formats apertures and sizes", () => {
    expect(formatAperture(1.4)).toBe("f/1.4");
    expect(formatAperture(8)).toBe("f/8");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(52_428_800)).toBe("50.0 MB");
  });

  it("builds an exposure line skipping unknowns", () => {
    expect(exposureLine({ focal_length: 50, aperture: 1.4, shutter_speed: 0.002, iso: 400 })).toBe(
      "50mm · f/1.4 · 1/500 · ISO 400",
    );
    expect(exposureLine({ focal_length: null, aperture: null, shutter_speed: null, iso: 100 })).toBe(
      "ISO 100",
    );
  });

  it("formats relative times", () => {
    const now = Date.parse("2026-10-01T12:00:00Z");
    expect(formatRelative("2026-10-01T11:59:58Z", now)).toBe("just now");
    expect(formatRelative("2026-10-01T11:55:00Z", now)).toBe("5 min ago");
    expect(formatRelative(null, now)).toBe("never");
  });

  it("title-cases identifiers", () => {
    expect(titleCase("good_hi_clip")).toBe("Good Hi Clip");
  });

  it("drops empty query params", () => {
    expect(
      toSearchParams({
        q: "",
        rating_min: 3,
        favorite: false,
        flag: undefined,
        hide_rejected: true,
      }).toString(),
    ).toBe("rating_min=3&hide_rejected=true");
  });
});
