import { safeParseJson, type StorageLike } from "./storage";

// Pinned answers — real, persisted in localStorage (same approach as
// conversations). Lets a user keep useful questions one click away.
const PINS_KEY = "companyKnowledgePins.v1";

export type PinnedItem = {
  id: string;
  question: string;
  topicId: string;
};

export function loadPins(storage: StorageLike = window.localStorage): PinnedItem[] {
  const parsed = safeParseJson<unknown[]>(storage.getItem(PINS_KEY), []);
  return parsed
    .map((value) => {
      if (!value || typeof value !== "object") {
        return null;
      }
      const item = value as Partial<PinnedItem>;
      if (!item.id || !item.question || !item.topicId) {
        return null;
      }
      return { id: String(item.id), question: String(item.question), topicId: String(item.topicId) };
    })
    .filter((item): item is PinnedItem => item !== null);
}

export function savePins(pins: PinnedItem[], storage: StorageLike = window.localStorage): void {
  storage.setItem(PINS_KEY, JSON.stringify(pins));
}

export function togglePin(pins: PinnedItem[], item: PinnedItem): PinnedItem[] {
  return pins.some((pin) => pin.id === item.id)
    ? pins.filter((pin) => pin.id !== item.id)
    : [item, ...pins];
}

export function isPinned(pins: PinnedItem[], id: string): boolean {
  return pins.some((pin) => pin.id === id);
}
