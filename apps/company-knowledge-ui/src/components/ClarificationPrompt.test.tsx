import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Clarification } from "../api/answers";
import { ChatMessage } from "./ChatMessage";
import { ClarificationPrompt } from "./ClarificationPrompt";

const clarification: Clarification = {
  prompt: "I found 2 topics that may contain what you're looking for. Which one do you mean?",
  original_question: "how do I reset my password",
  options: [
    { source_item_id: "page-vpn", title: "VPN Password Reset", section_path: "IT / Access" },
    { source_item_id: "page-email", title: "Email Password Reset", section_path: "IT / Mail" }
  ]
};

describe("ClarificationPrompt", () => {
  it("renders one button per candidate page", () => {
    const html = renderToStaticMarkup(
      <ClarificationPrompt clarification={clarification} onSelectOption={() => undefined} />
    );
    expect(html).toContain("Which one do you mean");
    expect(html).toContain("VPN Password Reset");
    expect(html).toContain("Email Password Reset");
    expect(html).not.toContain("disabled");
  });

  it("disables options once resolved", () => {
    const html = renderToStaticMarkup(
      <ClarificationPrompt clarification={clarification} resolved onSelectOption={() => undefined} />
    );
    expect(html).toContain("disabled");
    expect(html).toContain("answering from your choice");
  });
});

describe("ChatMessage clarification", () => {
  it("renders the picker and not the no-answer state when clarification is present", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          id: "msg-clarify",
          role: "assistant",
          content: clarification.prompt,
          citations: [],
          createdAt: "2026-06-06T10:00:00Z",
          status: "done",
          clarification
        }}
        onSelectQuestion={() => undefined}
      />
    );
    expect(html).toContain("Needs a quick clarification");
    expect(html).toContain("VPN Password Reset");
    expect(html).not.toContain("No grounded answer found");
  });
});
