import { describe, expect, it } from "vitest";

import {
  addAssistantPlaceholder,
  addUserMessage,
  completeAssistantMessage,
  conversationsForTopic,
  createConversation,
  deleteConversation,
  filterConversations,
  loadConversations,
  saveConversations,
  titleFromQuestion,
  upsertConversation
} from "./conversations";
import { MemoryStorage } from "./testStorage";

describe("conversation storage", () => {
  it("persists chat messages and groups them by topic", () => {
    const storage = new MemoryStorage();
    const conversation = createConversation("hr", new Date("2026-05-28T10:00:00Z"));
    const withUser = addUserMessage(conversation, "How do I request paid leave?", new Date("2026-05-28T10:01:00Z"));
    const withAssistant = addAssistantPlaceholder(withUser.conversation, new Date("2026-05-28T10:01:01Z"));
    const completed = completeAssistantMessage(
      withAssistant.conversation,
      withAssistant.messageId,
      "Use the leave request process.",
      [],
      [],
      new Date("2026-05-28T10:02:00Z")
    );

    saveConversations(upsertConversation([], completed), storage);
    const loaded = loadConversations(storage);

    expect(loaded).toHaveLength(1);
    expect(conversationsForTopic(loaded, "hr")[0].messages).toMatchObject([
      { role: "user", content: "How do I request paid leave?" },
      { role: "assistant", content: "Use the leave request process.", status: "done" }
    ]);
    expect(titleFromQuestion("  What documents do I need for onboarding?  ")).toBe(
      "What documents do I need for onboarding?"
    );
  });

  it("creates separate conversations, switches by topic, filters, and deletes", () => {
    const first = createConversation("hr", new Date("2026-05-28T10:00:00Z"));
    const second = createConversation("onboarding", new Date("2026-05-28T11:00:00Z"));
    const titled = addUserMessage(second, "What should I do on day one?", new Date("2026-05-28T11:01:00Z")).conversation;
    const conversations = [first, titled];

    expect(conversationsForTopic(conversations, "onboarding")).toHaveLength(1);
    expect(conversationsForTopic(conversations, "onboarding")[0].title).toBe("What should I do on day one?");
    expect(filterConversations(conversations, "day one")).toHaveLength(1);
    expect(deleteConversation(conversations, first.id)).toEqual([titled]);
  });
});
