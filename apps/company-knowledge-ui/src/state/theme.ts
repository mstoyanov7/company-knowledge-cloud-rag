import { safeParseJson, type StorageLike } from "./storage";

export type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "companyKnowledgeTheme.v1";

export function loadTheme(storage: StorageLike = window.localStorage): Theme {
  return safeParseJson<Theme>(storage.getItem(THEME_STORAGE_KEY), "light");
}

export function saveTheme(theme: Theme, storage: StorageLike = window.localStorage): void {
  storage.setItem(THEME_STORAGE_KEY, JSON.stringify(theme));
}

export function nextTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}
