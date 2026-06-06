import { AlertTriangle, Clock, Layers } from "lucide-react";

import type { Citation } from "../api/answers";
import { uniquePageCitations } from "../utils/citations";
import { formatUpdateTime, isStale } from "../utils/freshness";

type AnswerMetaProps = {
  citations: Citation[];
};

export function AnswerMeta({ citations }: AnswerMetaProps) {
  if (citations.length === 0) {
    return null;
  }

  const sourcePages = uniquePageCitations(citations);
  const newest = newestModified(sourcePages);
  const stale = newest ? isStale(newest) : false;

  return (
    <div className="answer-meta">
      <span className="chip-meta">
        <Layers size={12} aria-hidden="true" /> Based on{" "}
        <b>
          {sourcePages.length} page{sourcePages.length > 1 ? "s" : ""}
        </b>
      </span>
      {newest ? (
        <span className={stale ? "chip-meta chip-meta--warn" : "chip-meta"}>
          <Clock size={12} aria-hidden="true" /> Source updated {formatUpdateTime(newest)}
        </span>
      ) : null}
      {stale ? (
        <span className="chip-meta chip-meta--warn">
          <AlertTriangle size={12} aria-hidden="true" /> Verify before relying
        </span>
      ) : null}
    </div>
  );
}

function newestModified(citations: Citation[]): string | null {
  let newest: number | null = null;
  let raw: string | null = null;
  for (const citation of citations) {
    if (!citation.last_modified_utc) {
      continue;
    }
    const time = new Date(citation.last_modified_utc).getTime();
    if (Number.isNaN(time)) {
      continue;
    }
    if (newest === null || time > newest) {
      newest = time;
      raw = citation.last_modified_utc;
    }
  }
  return raw;
}
