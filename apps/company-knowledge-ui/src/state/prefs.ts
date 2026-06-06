import { safeParseJson, type StorageLike } from "./storage";

// Appearance preferences beyond theme: density + accent hue. These are pure
// CSS-token tweaks (the prototype's "Tweaks" panel) and are real, not mocked.
export type Density = "cozy" | "compact" | "dense";
export type AccentHue = 45 | 250 | 160 | 20;

export type Prefs = {
  density: Density;
  accentHue: AccentHue;
};

const PREFS_KEY = "companyKnowledgePrefs.v1";

const defaultPrefs: Prefs = { density: "compact", accentHue: 45 };

export function loadPrefs(storage: StorageLike = window.localStorage): Prefs {
  const parsed = safeParseJson<Partial<Prefs> | null>(storage.getItem(PREFS_KEY), null);
  if (!parsed || typeof parsed !== "object") {
    return { ...defaultPrefs };
  }
  const density: Density =
    parsed.density === "cozy" || parsed.density === "dense" ? parsed.density : "compact";
  const accentHue: AccentHue = ([45, 250, 160, 20] as AccentHue[]).includes(parsed.accentHue as AccentHue)
    ? (parsed.accentHue as AccentHue)
    : 45;
  return { density, accentHue };
}

export function savePrefs(prefs: Prefs, storage: StorageLike = window.localStorage): void {
  storage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

export function applyPrefs(prefs: Prefs): void {
  const root = document.documentElement;
  root.dataset.density = prefs.density;
  root.style.setProperty("--accent-h", String(prefs.accentHue));
}
