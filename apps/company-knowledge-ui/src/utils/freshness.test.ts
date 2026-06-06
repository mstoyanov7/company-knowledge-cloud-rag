import { afterEach, describe, expect, it, vi } from "vitest";

import { formatUpdateTime } from "./freshness";

describe("formatUpdateTime", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("formats today's updates as elapsed seconds, minutes, or hours", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-05T12:00:00Z"));

    expect(formatUpdateTime("2026-06-05T11:59:35Z")).toBe("25 seconds ago");
    expect(formatUpdateTime("2026-06-05T11:52:00Z")).toBe("8 minutes ago");
    expect(formatUpdateTime("2026-06-05T09:00:00Z")).toBe("3 hours ago");
  });

  it("formats older updates as day dot month", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-05T12:00:00Z"));

    expect(formatUpdateTime("2026-05-03T09:00:00Z")).toBe("03.05");
  });
});
