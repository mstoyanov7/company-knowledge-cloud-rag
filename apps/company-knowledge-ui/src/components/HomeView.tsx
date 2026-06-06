import { ArrowRight, Layers, RefreshCw, Sparkles, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchRecentlyUpdatedDocuments, type DocumentSummary } from "../api/documents";
import type { Topic } from "../api/topics";
import { fetchTrendingQuestions, type TrendingQuestion } from "../api/trending";
import { formatUpdateTime } from "../utils/freshness";
import { firstNameOf } from "../utils/user";
import { getTopicIcon } from "./topicIcon";

const RECENTLY_UPDATED_LIMIT = 3;
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

      <DocumentGroup items={updated} onOpenDocument={onOpenDocument} />

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
  onOpenDocument
}: {
  items: DocumentSummary[];
  onOpenDocument: (document: DocumentSummary) => void;
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

