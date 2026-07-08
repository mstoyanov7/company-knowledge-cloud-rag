import { scopedKey } from "./scope";
import { safeParseJson, type StorageLike } from "./storage";

// Pinned chat sessions, persisted in localStorage alongside conversations.
const PINS_KEY = "companyKnowledgePins.v1";

export type PinnedItem = {
  id: string;
  title: string;
  topicId: string;
};

export function loadPins(storage: StorageLike = window.localStorage): PinnedItem[] {
  const parsed = safeParseJson<unknown[]>(storage.getItem(scopedKey(PINS_KEY)), []);
  return parsed
    .map((value) => {
      if (!value || typeof value !== "object") {
        return null;
      }
      const item = value as Partial<PinnedItem> & { question?: string };
      const title = item.title || item.question;
      if (!item.id || !title || !item.topicId) {
        return null;
      }
      return { id: String(item.id), title: String(title), topicId: String(item.topicId) };
    })
    .filter((item): item is PinnedItem => item !== null);
}

export function savePins(pins: PinnedItem[], storage: StorageLike = window.localStorage): void {
  storage.setItem(scopedKey(PINS_KEY), JSON.stringify(pins));
}

export function togglePin(pins: PinnedItem[], item: PinnedItem): PinnedItem[] {
  return pins.some((pin) => pin.id === item.id)
    ? pins.filter((pin) => pin.id !== item.id)
    : [item, ...pins];
}

export function isPinned(pins: PinnedItem[], id: string): boolean {
  return pins.some((pin) => pin.id === id);
}
