import { ChevronRight, Clock, Download, ExternalLink, Monitor, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { Citation } from "../api/answers";
import { downloadApiFile, isApiDownloadUrl } from "../api/client";
import { fetchDocumentDetail, type DocumentSummary } from "../api/documents";
import type { NotebookPage } from "../api/notebooks";
import { attachmentCitationInfo } from "../utils/citations";
import { formatUpdateTime, isStale } from "../utils/freshness";
import { initialsOf } from "../utils/user";

export type PanelSource = {
  index?: number;
  title: string;
  sourceItemId?: string;
  sourceSystem?: string;
  segments: string[];
  body: string;
  age: string | null;
  stale: boolean;
  editedFull?: string;
  editor?: string;
  editorInit?: string;
  url?: string;
  clientUrl?: string;
  downloadUrl?: string;
  downloadFileName?: string;
  actions?: PanelSourceAction[];
};

export type PanelSourceAction = {
  label: string;
  question: string;
  topicId: string;
};

type SourcePanelProps = {
  source: PanelSource | null;
  onClose: () => void;
  onAskSource?: (action: PanelSourceAction) => void;
};

export function SourcePanel({ source, onClose, onAskSource }: SourcePanelProps) {
  const [detailText, setDetailText] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!source?.sourceItemId) {
      setDetailText("");
      setDetailLoading(false);
      setDetailError(null);
      return;
    }

    let isCurrent = true;
    setDetailText("");
    setDetailLoading(true);
    setDetailError(null);
    fetchDocumentDetail(source.sourceItemId, source.sourceSystem)
      .then((detail) => {
        if (isCurrent) {
          setDetailText(detail.content_text || "");
        }
      })
      .catch((error: Error) => {
        if (isCurrent) {
          setDetailError(error.message);
        }
      })
      .finally(() => {
        if (isCurrent) {
          setDetailLoading(false);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [source?.sourceItemId, source?.sourceSystem]);

  if (!source) {
    return <aside className="source" id="source-panel" aria-hidden="true" />;
  }

  return (
    <aside className="source" id="source-panel" aria-hidden="false">
      <div className="source__head">
        <span className="source__kicker">
          {typeof source.index === "number" ? <span className="source__n">{source.index}</span> : null}
          Source
        </span>
        <div className="topbar__spacer" />
        <button className="iconbtn" type="button" onClick={onClose} aria-label="Close source">
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="source__scroll scroll">
        {source.segments.length > 0 ? (
          <div className="onenote-path">
            {source.segments.map((segment, index) => (
              <span key={`${segment}-${index}`} style={{ display: "contents" }}>
                <span className={index === source.segments.length - 1 ? "seg2 is-page" : "seg2"}>{segment}</span>
                {index < source.segments.length - 1 ? <ChevronRight size={12} aria-hidden="true" /> : null}
              </span>
            ))}
          </div>
        ) : null}

        <h2 className="source__title">{source.title}</h2>

        {source.editor ? (
          <div className="source__byline">
            <span className="ed">
              <span className="mini-ava">{source.editorInit || initialsOf(source.editor)}</span>
              {source.editor}
            </span>
            {source.editedFull ? (
              <>
                <span>-</span>
                <span>Last edited {source.editedFull}</span>
              </>
            ) : null}
          </div>
        ) : null}

        {source.age ? (
          <div className="source__freshrow">
            <span className={source.stale ? "chip-meta chip-meta--warn" : "chip-meta"}>
              <Clock size={12} aria-hidden="true" /> Updated {source.age}
            </span>
          </div>
        ) : null}

        {detailLoading ? (
          <p className="source__empty">Loading source text...</p>
        ) : detailError ? (
          <p className="source__empty">{detailError}</p>
        ) : detailText ? (
          <div className="source__doc">
            <div className="relevant-flag">Raw parsed source text</div>
            <pre className="source__raw">{detailText}</pre>
          </div>
        ) : source.sourceItemId ? (
          <p className="source__empty">No parsed source text was returned for this source.</p>
        ) : source.body ? (
          <div className="source__doc">
            <div className="relevant-flag">Most relevant excerpt</div>
            <p className="source__mark">{source.body}</p>
          </div>
        ) : (
          <p className="source__empty">No preview text was returned for this source.</p>
        )}

        {source.actions?.length && onAskSource ? (
          <div className="source__actions">
            {source.actions.map((action) => (
              <button
                key={`${action.topicId}-${action.question}`}
                className="source-action"
                type="button"
                onClick={() => onAskSource(action)}
              >
                <span className="source-action__ic">
                  <Sparkles size={15} aria-hidden="true" />
                </span>
                <span>{action.label}</span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="source__links">
          {source.downloadUrl ? (
            <button className="deeplink" type="button" onClick={() => downloadSource(source)}>
              <span className="deeplink__ic">
                <Download size={16} aria-hidden="true" />
              </span>
              <span className="deeplink__main">
                <b>Download attachment</b>
                <span>{source.downloadFileName || shortUrl(source.downloadUrl)}</span>
              </span>
              <span className="deeplink__go">
                <Download size={15} aria-hidden="true" />
              </span>
            </button>
          ) : null}
          {source.url ? (
            <a className="deeplink" href={source.url} target="_blank" rel="noreferrer">
              <span className="deeplink__ic">
                <ExternalLink size={16} aria-hidden="true" />
              </span>
              <span className="deeplink__main">
                <b>Open in OneNote for the web</b>
                <span>{shortUrl(source.url)}</span>
              </span>
              <span className="deeplink__go">
                <ExternalLink size={15} aria-hidden="true" />
              </span>
            </a>
          ) : null}
          {source.clientUrl ? (
            <a className="deeplink" href={source.clientUrl}>
              <span className="deeplink__ic">
                <Monitor size={16} aria-hidden="true" />
              </span>
              <span className="deeplink__main">
                <b>Open in OneNote desktop</b>
                <span>{shortUrl(source.clientUrl)}</span>
              </span>
              <span className="deeplink__go">
                <ExternalLink size={15} aria-hidden="true" />
              </span>
            </a>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function shortUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`.slice(0, 48);
  } catch {
    return url.slice(0, 48);
  }
}

export function citationToPanelSource(citation: Citation): PanelSource {
  const age = citation.last_modified_utc ? formatUpdateTime(citation.last_modified_utc) : null;
  const stale = citation.last_modified_utc ? isStale(citation.last_modified_utc) : false;
  const raw = citation.section_path || citation.source_container || "";
  const segments = pathSegments(raw);
  const attachmentInfo = attachmentCitationInfo(citation);
  return {
    index: citation.index,
    title: attachmentInfo ? `Page: ${attachmentInfo.page} | File: ${attachmentInfo.file}` : citation.title,
    sourceItemId: citation.source_item_id,
    sourceSystem: citation.source_system,
    segments: segments.length > 0 ? segments : sourceSystemSegments(citation.source_system),
    body: citation.snippet || "",
    age,
    stale,
    editedFull: citation.last_modified_utc ? formatAbsoluteDate(citation.last_modified_utc) : undefined,
    editor: citation.last_edited_by || undefined,
    editorInit: citation.last_edited_by ? initialsOf(citation.last_edited_by) : undefined,
    url: citation.source_url && !isApiDownloadUrl(citation.source_url) ? citation.source_url : undefined,
    clientUrl: citation.client_url || undefined,
    downloadUrl: typeof citation.metadata?.download_url === "string" ? citation.metadata.download_url : undefined,
    downloadFileName:
      typeof citation.metadata?.attachment_file_name === "string" ? citation.metadata.attachment_file_name : undefined
  };
}

export function documentToPanelSource(source: NotebookPage | DocumentSummary, index?: number): PanelSource {
  const updateTime = source.updated_at_utc || source.last_modified_utc;
  const age = updateTime ? formatUpdateTime(updateTime) : null;
  const stale = source.last_modified_utc ? isStale(source.last_modified_utc) : false;
  const raw = source.section_path || source.source_container || "";
  const segments = pathSegments(raw);
  return {
    index,
    title: source.title,
    sourceItemId: source.source_item_id,
    sourceSystem: source.source_system,
    segments: segments.length > 0 ? segments : sourceSystemSegments(source.source_system),
    body: source.snippet || "",
    age,
    stale,
    editedFull: source.last_modified_utc ? formatAbsoluteDate(source.last_modified_utc) : undefined,
    editor: source.last_edited_by || undefined,
    editorInit: source.last_edited_by ? initialsOf(source.last_edited_by) : undefined,
    url: source.source_url || undefined,
    clientUrl: source.client_url || undefined
  };
}

function pathSegments(raw: string): string[] {
  return raw
    .split(/[/>]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function sourceSystemSegments(sourceSystem: string): string[] {
  if (!sourceSystem) {
    return [];
  }
  return [
    sourceSystem
      .split(/[-_\s]+/)
      .filter(Boolean)
      .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
      .join(" ")
  ];
}

function formatAbsoluteDate(value: string): string {
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

async function downloadSource(source: PanelSource): Promise<void> {
  if (!source.downloadUrl) {
    return;
  }
  if (isApiDownloadUrl(source.downloadUrl)) {
    await downloadApiFile(source.downloadUrl, source.downloadFileName);
    return;
  }
  window.open(source.downloadUrl, "_blank", "noreferrer");
}
