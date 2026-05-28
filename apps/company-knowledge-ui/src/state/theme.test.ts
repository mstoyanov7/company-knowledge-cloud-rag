import { describe, expect, it } from "vitest";

import { loadTheme, nextTheme, saveTheme } from "./theme";
import { MemoryStorage } from "./testStorage";

describe("theme storage", () => {
  it("persists the selected theme", () => {
    const storage = new MemoryStorage();

    saveTheme("dark", storage);

    expect(loadTheme(storage)).toBe("dark");
    expect(nextTheme("dark")).toBe("light");
  });
});
