import { Download, ExternalLink } from "lucide-react";

import type { Citation } from "../api/answers";
import { downloadApiFile, isApiDownloadUrl } from "../api/client";
import { attachmentCitationInfo, uniquePageCitations } from "../utils/citations";
import { formatUpdateTime } from "../utils/freshness";

type CitationListProps = {
  citations: Citation[];
  onOpenSource?: (citation: Citation) => void;
};

export function CitationList({ citations, onOpenSource }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }
  const sourcePages = uniquePageCitations(citations);

  return (
    <details className="citation-list" aria-label="Sources" open>
      <summary>Sources ({sourcePages.length})</summary>
      <ul>
        {sourcePages.map((citation, index) => {
          const downloadUrl = citationDownloadUrl(citation);
          const attachmentInfo = attachmentCitationInfo(citation);
          return (
          <li key={citation.source_item_id || `${citation.title}-${citation.source_url}-${index}`}>
            <button
              type="button"
              className="citation-open"
              onClick={() => onOpenSource?.(citation)}
              aria-label={`Open ${citation.title}`}
            >
              <span className="citation-open__n">{citation.index ?? index + 1}</span>
              <span className="citation-open__main">
                {attachmentInfo ? (
                  <>
                    <strong>Page: {attachmentInfo.page}</strong>
                    <span>File: {attachmentInfo.file}</span>
                  </>
                ) : (
                  <strong>{citation.title}</strong>
                )}
                <span>{sourceLabel(citation.source_system)}</span>
                {citation.section_path ? <span>{citation.section_path}</span> : null}
                {citation.last_modified_utc ? <span>Updated {formatUpdateTime(citation.last_modified_utc)}</span> : null}
              </span>
            </button>
            {downloadUrl ? (
              <button
                type="button"
                className="citation-ext"
                onClick={() => downloadCitation(citation, downloadUrl)}
                aria-label={`Download ${citation.title}`}
              >
                <Download size={16} aria-hidden="true" />
              </button>
            ) : null}
            {citation.source_url ? (
              <a
                className="citation-ext"
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Open ${citation.title} in a new tab`}
              >
                <ExternalLink size={16} aria-hidden="true" />
              </a>
            ) : null}
          </li>
          );
        })}
      </ul>
    </details>
  );
}

function citationDownloadUrl(citation: Citation): string {
  const value = citation.metadata?.download_url;
  return typeof value === "string" ? value : "";
}

async function downloadCitation(citation: Citation, downloadUrl: string): Promise<void> {
  const fileName = typeof citation.metadata?.attachment_file_name === "string" ? citation.metadata.attachment_file_name : citation.title;
  if (isApiDownloadUrl(downloadUrl)) {
    await downloadApiFile(downloadUrl, fileName);
    return;
  }
  window.open(downloadUrl, "_blank", "noreferrer");
}

function sourceLabel(sourceSystem: string): string {
  if (!sourceSystem) {
    return "Source";
  }
  return sourceSystem
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}
