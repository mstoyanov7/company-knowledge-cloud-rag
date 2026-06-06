import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatMessage } from "./ChatMessage";
import { MarkdownAnswer } from "./MarkdownAnswer";

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
              source_item_id: "onenote:deployment",
              source_system: "onenote",
              source_url: "https://example.test/deployment",
              section_path: "Engineering / Releases",
              last_modified_utc: "2026-05-01T00:00:00Z"
            },
            {
              title: "Deployment Guide",
              source_item_id: "onenote:deployment",
              source_system: "onenote",
              source_url: "https://example.test/deployment",
              section_path: "Engineering / Releases",
              last_modified_utc: "2026-05-01T00:00:00Z"
            }
          ],
          downloads: [
            {
              download_id: "download-1",
              file_name: "guide.txt",
              file_extension: "txt",
              size_bytes: 11,
              readable: true,
              parent_source_item_id: "onenote:page-1",
              parent_title: "Deployment Guide",
              download_url: "/api/v1/attachments/download-1/download"
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
    expect(html).toContain("Based on <b>1 page</b>");
    expect(html).toContain("Deployment Guide");
    expect(html).toContain("Downloads");
    expect(html).toContain("guide.txt");
  });

  it("renders fenced code blocks with a copy control", () => {
    const html = renderToStaticMarkup(
      <MarkdownAnswer answer={"Run the stack:\n\n```powershell\ndocker compose up -d --build rag-api\n```"} />
    );

    expect(html).toContain("codeblock");
    expect(html).toContain("powershell");
    expect(html).toContain("Copy");
    expect(html).toContain("docker compose up -d --build rag-api");
    expect(html).not.toContain("```");
  });
});
