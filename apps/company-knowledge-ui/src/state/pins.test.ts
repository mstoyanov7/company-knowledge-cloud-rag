import { describe, expect, it } from "vitest";

import { isPinned, loadPins, savePins, togglePin, type PinnedItem } from "./pins";
import { MemoryStorage } from "./testStorage";

describe("pinned chat sessions", () => {
  it("persists pinned conversations by title and topic", () => {
    const storage = new MemoryStorage();
    const pin: PinnedItem = {
      id: "conv-1",
      title: "First week onboarding",
      topicId: "section-onboarding"
    };

    savePins([pin], storage);

    expect(loadPins(storage)).toEqual([pin]);
    expect(isPinned(loadPins(storage), "conv-1")).toBe(true);
  });

  it("migrates older pinned question entries to chat titles", () => {
    const storage = new MemoryStorage();
    storage.setItem(
      "companyKnowledgePins.v1",
      JSON.stringify([{ id: "conv-2", question: "Legacy saved question", topicId: "section-people" }])
    );

    expect(loadPins(storage)).toEqual([
      { id: "conv-2", title: "Legacy saved question", topicId: "section-people" }
    ]);
  });

  it("toggles a conversation pin by conversation id", () => {
    const pin: PinnedItem = { id: "conv-3", title: "Release checklist", topicId: "section-releases" };

    expect(togglePin([], pin)).toEqual([pin]);
    expect(togglePin([pin], pin)).toEqual([]);
  });
});
