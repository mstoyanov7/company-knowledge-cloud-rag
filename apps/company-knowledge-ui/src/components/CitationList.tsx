import { ExternalLink } from "lucide-react";

import type { Citation } from "../api/answers";

type CitationListProps = {
  citations: Citation[];
};

export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <details className="citation-list" aria-label="Sources">
      <summary>Sources ({citations.length})</summary>
      <ul>
        {citations.map((citation, index) => (
          <li key={`${citation.title}-${citation.source_url}-${index}`}>
            <div>
              <strong>{citation.title}</strong>
              <span>{sourceLabel(citation.source_system)}</span>
              {citation.section_path ? <span>{citation.section_path}</span> : null}
              {citation.last_modified_utc ? <span>Updated {formatDate(citation.last_modified_utc)}</span> : null}
            </div>
            {citation.source_url ? (
              <a href={citation.source_url} target="_blank" rel="noreferrer" aria-label={`Open ${citation.title}`}>
                <ExternalLink size={16} aria-hidden="true" />
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
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

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(date);
}
