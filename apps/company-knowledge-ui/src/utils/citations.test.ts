import { describe, expect, it } from "vitest";

import type { Citation } from "../api/answers";
import { attachmentCitationInfo, uniquePageCitations } from "./citations";

function citation(update: Partial<Citation>): Citation {
  return {
    title: "abc",
    source_item_id: "onenote:page-abc",
    source_system: "onenote",
    source_url: "https://example.test/page-abc",
    last_modified_utc: "2026-06-01T00:00:00Z",
    ...update
  };
}

describe("citation utilities", () => {
  it("does not hide readable attachment citations behind the parent page", () => {
    const page = citation({ index: 1, title: "abc" });
    const attachment = citation({
      index: 2,
      title: "Page: abc | File: file.docx",
      source_item_id: "onenote-attachment:file.docx",
      source_url: "/api/v1/attachments/download-file.docx/download",
      metadata: {
        document_kind: "attachment",
        download_id: "download-file.docx",
        parent_source_item_id: "onenote:page-abc",
        parent_title: "abc",
        attachment_file_name: "file.docx"
      }
    });

    const deduped = uniquePageCitations([page, attachment]);

    expect(deduped).toHaveLength(2);
    expect(deduped.map((item) => item.title)).toEqual(["abc", "Page: abc | File: file.docx"]);
    expect(attachmentCitationInfo(attachment)).toEqual({ page: "abc", file: "file.docx" });
  });
});
