import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatMessage } from "./ChatMessage";

describe("ChatMessage", () => {
  it("renders assistant markdown and citations", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          id: "msg-1",
          role: "assistant",
          content: "### Deployment\n\n- Check production settings.",
          citations: [
            {
              title: "Deployment Guide",
              source_system: "onenote",
              source_url: "https://example.test/deployment",
              section_path: "Engineering / Releases",
              last_modified_utc: "2026-05-01T00:00:00Z"
            }
          ],
          createdAt: "2026-05-28T10:00:00Z",
          status: "done"
        }}
        onSelectQuestion={() => undefined}
      />
    );

    expect(html).toContain("<h3>Deployment</h3>");
    expect(html).toContain("Check production settings");
    expect(html).toContain("Sources (1)");
    expect(html).toContain("Deployment Guide");
  });
});
