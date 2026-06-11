import { ArrowRight, ChevronLeft, ChevronRight, Layers, Maximize2, RefreshCw, Sparkles, TrendingUp, X } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchRecentlyUpdatedDocuments, type DocumentSummary } from "../api/documents";
import type { Topic } from "../api/topics";
import { fetchTrendingQuestions, type TrendingQuestion } from "../api/trending";
import { formatUpdateTime } from "../utils/freshness";
import { firstNameOf } from "../utils/user";
import { getTopicIcon } from "./topicIcon";

const RECENTLY_UPDATED_LIMIT = 3;
const EXPANDED_RECENTLY_UPDATED_LIMIT = 20;
const RECENTLY_UPDATED_PAGE_SIZE = 5;
const TRENDING_QUESTIONS_LIMIT = 3;

type HomeViewProps = {
  userName: string;
  topics: Topic[];
  onSelectTopic: (topicId: string) => void;
  onAsk: (item: { question: string; topicId: string }) => void;
  onOpenDocument: (document: DocumentSummary) => void;
};

export function HomeView({ userName, topics, onSelectTopic, onAsk, onOpenDocument }: HomeViewProps) {
  const [updated, setUpdated] = useState<DocumentSummary[]>([]);
  const [expandedUpdated, setExpandedUpdated] = useState<DocumentSummary[]>([]);
  const [isUpdatesOpen, setIsUpdatesOpen] = useState(false);
  const [isUpdatesLoading, setIsUpdatesLoading] = useState(false);
  const [updatesError, setUpdatesError] = useState<string | null>(null);
  const [updatesPage, setUpdatesPage] = useState(0);
  const [trending, setTrending] = useState<TrendingQuestion[]>([]);

  useEffect(() => {
    let isCurrent = true;
    const loadHomeData = () => {
      Promise.allSettled([
        fetchRecentlyUpdatedDocuments(RECENTLY_UPDATED_LIMIT),
        fetchTrendingQuestions({ limit: TRENDING_QUESTIONS_LIMIT })
      ]).then((results) => {
        if (!isCurrent) {
          return;
        }
        const [documentsResult, trendingResult] = results;
        setUpdated(documentsResult.status === "fulfilled" ? documentsResult.value.slice(0, RECENTLY_UPDATED_LIMIT) : []);
        setTrending(trendingResult.status === "fulfilled" ? trendingResult.value.slice(0, TRENDING_QUESTIONS_LIMIT) : []);
      });
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState !== "hidden") {
        loadHomeData();
      }
    };

    loadHomeData();
    window.addEventListener("focus", loadHomeData);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    const interval = window.setInterval(refreshWhenVisible, 60_000);
    return () => {
      isCurrent = false;
      window.removeEventListener("focus", loadHomeData);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.clearInterval(interval);
    };
  }, []);

  const topicIds = new Set(topics.map((topic) => topic.id));
  const scopedTrending = trending
    .filter((item) => item.topic_id && topicIds.has(item.topic_id))
    .slice(0, TRENDING_QUESTIONS_LIMIT);

  function loadExpandedUpdates() {
    setIsUpdatesLoading(true);
    setUpdatesError(null);
    fetchRecentlyUpdatedDocuments(EXPANDED_RECENTLY_UPDATED_LIMIT)
      .then((items) => {
        setExpandedUpdated(items.slice(0, EXPANDED_RECENTLY_UPDATED_LIMIT));
        setUpdatesPage(0);
      })
      .catch(() => setUpdatesError("Could not load recent updates."))
      .finally(() => setIsUpdatesLoading(false));
  }

  function openUpdatesWindow() {
    setIsUpdatesOpen(true);
    loadExpandedUpdates();
  }

  function openExpandedDocument(document: DocumentSummary) {
    setIsUpdatesOpen(false);
    onOpenDocument(document);
  }

  return (
    <div className="home fade-in">
      <div className="home__hello">
        <span className="home__sun">
          <Sparkles size={19} aria-hidden="true" />
        </span>
        <h1>Good to see you, {firstNameOf(userName)}.</h1>
      </div>
      <p className="home__lead">
        Ask anything across the company knowledge base - every answer is grounded in source pages you can open
        and verify. Pick a topic to start.
      </p>

      <DocumentGroup items={updated} onOpenDocument={onOpenDocument} onExpand={openUpdatesWindow} />

      {isUpdatesOpen ? (
        <RecentUpdatesModal
          items={expandedUpdated}
          isLoading={isUpdatesLoading}
          error={updatesError}
          page={updatesPage}
          onPageChange={setUpdatesPage}
          onClose={() => setIsUpdatesOpen(false)}
          onOpenDocument={openExpandedDocument}
          onRetry={loadExpandedUpdates}
        />
      ) : null}

      <TrendingGroup items={scopedTrending} onAsk={onAsk} />

      <div className="home__group">
        <div className="home__grouph">
          <span className="ic">
            <Layers size={13} aria-hidden="true" />
          </span>
          <b>Browse by topic</b>
          <span className="sub">choose where to scope your question</span>
        </div>
        <div className="topic-grid">
          {topics.map((topic) => {
            const Icon = getTopicIcon(topic.icon);
            return (
              <button
                key={topic.id}
                type="button"
                className="topic-card"
                onClick={() => onSelectTopic(topic.id)}
              >
                <div className="topic-card__top">
                  <span className="topic-card__ic">
                    <Icon size={16} aria-hidden="true" />
                  </span>
                  <span className="topic-card__arrow">
                    <ArrowRight size={15} aria-hidden="true" />
                  </span>
                </div>
                <div className="topic-card__name">{topic.name}</div>
                <div className="topic-card__desc">{topic.description}</div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DocumentGroup({
  items,
  onOpenDocument,
  onExpand
}: {
  items: DocumentSummary[];
  onOpenDocument: (document: DocumentSummary) => void;
  onExpand: () => void;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="home__group">
      <div className="home__grouph">
        <span className="ic">
          <RefreshCw size={13} aria-hidden="true" />
        </span>
        <b>Recently updated</b>
        <span className="sub">docs that changed recently</span>
        <span className="home__headSpacer" />
        <button className="btn btn--ghost btn--sm home__groupAction" type="button" onClick={onExpand}>
          <Maximize2 size={13} aria-hidden="true" />
          View 20
        </button>
      </div>
      <div className="starts">
        {items.map((item) => (
          <button key={item.source_item_id} type="button" className="start" onClick={() => onOpenDocument(item)}>
            <span className="start__q">{item.title}</span>
            <span className="start__meta">
              <span className="start__badge start__badge--fresh">
                <RefreshCw size={11} aria-hidden="true" />
                {formatUpdateTime(item.updated_at_utc || item.last_modified_utc)}
              </span>
              <span className="start__arrow">
                <ArrowRight size={14} aria-hidden="true" />
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function RecentUpdatesModal({
  items,
  isLoading,
  error,
  page,
  onPageChange,
  onClose,
  onOpenDocument,
  onRetry
}: {
  items: DocumentSummary[];
  isLoading: boolean;
  error: string | null;
  page: number;
  onPageChange: (page: number) => void;
  onClose: () => void;
  onOpenDocument: (document: DocumentSummary) => void;
  onRetry: () => void;
}) {
  const pageCount = Math.max(1, Math.ceil(items.length / RECENTLY_UPDATED_PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const firstItem = safePage * RECENTLY_UPDATED_PAGE_SIZE;
  const pageItems = items.slice(firstItem, firstItem + RECENTLY_UPDATED_PAGE_SIZE);
  const rangeStart = items.length === 0 ? 0 : firstItem + 1;
  const rangeEnd = Math.min(firstItem + RECENTLY_UPDATED_PAGE_SIZE, items.length);

  return (
    <div className="modal-host">
      <div className="modal__scrim" onClick={onClose} />
      <div className="modal modal--updates" role="dialog" aria-label="Recently updated" aria-modal="true">
        <button className="modal__x" type="button" onClick={onClose} aria-label="Close">
          <X size={17} aria-hidden="true" />
        </button>
        <div className="updates-modal__head">
          <span className="updates-modal__icon">
            <RefreshCw size={17} aria-hidden="true" />
          </span>
          <div>
            <h2>Recently updated</h2>
            <p>Last {EXPANDED_RECENTLY_UPDATED_LIMIT} document updates</p>
          </div>
        </div>

        <div className="updates-modal__body">
          {isLoading ? (
            <div className="updates-modal__state">Loading updates...</div>
          ) : error ? (
            <div className="updates-modal__state">
              <span>{error}</span>
              <button className="btn btn--sm" type="button" onClick={onRetry}>
                <RefreshCw size={13} aria-hidden="true" />
                Retry
              </button>
            </div>
          ) : pageItems.length === 0 ? (
            <div className="updates-modal__state">No recent updates found.</div>
          ) : (
            <div className="updates-list">
              {pageItems.map((item) => (
                <button
                  key={item.source_item_id}
                  type="button"
                  className="update-row"
                  onClick={() => onOpenDocument(item)}
                >
                  <span className="update-row__main">
                    <span className="update-row__title">{item.title}</span>
                    <span className="update-row__section">{item.section_path || item.source_container || item.source_system}</span>
                  </span>
                  <span className="update-row__meta">
                    <span className="start__badge start__badge--fresh">
                      <RefreshCw size={11} aria-hidden="true" />
                      {formatUpdateTime(item.updated_at_utc || item.last_modified_utc)}
                    </span>
                    <ArrowRight size={14} aria-hidden="true" />
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="updates-modal__foot">
          <span>
            {rangeStart}-{rangeEnd} of {items.length}
          </span>
          <div className="updates-modal__pager">
            <button
              className="btn btn--sm"
              type="button"
              onClick={() => onPageChange(Math.max(0, safePage - 1))}
              disabled={safePage === 0 || items.length === 0}
            >
              <ChevronLeft size={14} aria-hidden="true" />
              Prev
            </button>
            <span>
              {safePage + 1} / {pageCount}
            </span>
            <button
              className="btn btn--sm"
              type="button"
              onClick={() => onPageChange(Math.min(pageCount - 1, safePage + 1))}
              disabled={safePage >= pageCount - 1 || items.length === 0}
            >
              Next
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TrendingGroup({
  items,
  onAsk
}: {
  items: TrendingQuestion[];
  onAsk: (item: { question: string; topicId: string }) => void;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="home__group">
      <div className="home__grouph">
        <span className="ic">
          <TrendingUp size={13} aria-hidden="true" />
        </span>
        <b>Trending questions</b>
        <span className="sub">what colleagues are asking</span>
      </div>
      <div className="starts">
        {items.map((item) => (
          <button
            key={`${item.topic_id}-${item.question}`}
            type="button"
            className="start"
            onClick={() => item.topic_id && onAsk({ question: item.question, topicId: item.topic_id })}
          >
            <span className="start__q">{item.question}</span>
            <span className="start__meta">
              <span className="start__badge start__badge--hot">
                <TrendingUp size={11} aria-hidden="true" />
                asked {item.count}x
              </span>
              <span className="start__arrow">
                <ArrowRight size={14} aria-hidden="true" />
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

