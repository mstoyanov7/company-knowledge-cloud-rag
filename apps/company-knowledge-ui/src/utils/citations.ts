import type { Citation } from "../api/answers";

export function uniquePageCitations(citations: Citation[]): Citation[] {
  const byPage = new Map<string, Citation>();
  for (const citation of citations) {
    const key = citationDedupeKey(citation);
    const existing = byPage.get(key);
    if (!existing || citationIsNewer(citation, existing)) {
      byPage.set(key, citation);
    }
  }
  return Array.from(byPage.values()).sort((left, right) => (left.index ?? 0) - (right.index ?? 0));
}

export function attachmentCitationInfo(citation: Citation): { page: string; file: string } | null {
  const metadata = citation.metadata || {};
  if (metadata.document_kind !== "attachment") {
    return null;
  }
  const page = stringValue(metadata.citation_page_title) || stringValue(metadata.parent_title);
  const file =
    stringValue(metadata.citation_file_name) ||
    stringValue(metadata.attachment_file_name) ||
    stringValue(metadata.file_name);
  if (!page || !file) {
    return null;
  }
  return { page, file };
}

function citationDedupeKey(citation: Citation): string {
  const attachment = attachmentCitationInfo(citation);
  if (attachment) {
    const downloadId = stringValue(citation.metadata?.download_id);
    const indexedId = stringValue(citation.metadata?.indexed_source_item_id);
    return `attachment:${downloadId || indexedId || citation.source_item_id || citation.source_url || attachment.file}`;
  }
  return citation.source_item_id || citation.source_url || `${citation.source_system}:${citation.title}`;
}

function citationIsNewer(left: Citation, right: Citation): boolean {
  const leftTime = left.last_modified_utc ? new Date(left.last_modified_utc).getTime() : Number.NEGATIVE_INFINITY;
  const rightTime = right.last_modified_utc ? new Date(right.last_modified_utc).getTime() : Number.NEGATIVE_INFINITY;
  return leftTime > rightTime;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
