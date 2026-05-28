import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { Topic } from "../api/topics";
import { ThemeToggle } from "../components/ThemeToggle";
import { TopicGrid } from "../components/TopicGrid";
import type { Theme } from "../state/theme";

type TopicSelectionPageProps = {
  topics: Topic[];
  theme: Theme;
  onToggleTheme: () => void;
  onSelectTopic: (topicId: string) => void;
};

export function TopicSelectionPage({ topics, theme, onToggleTheme, onSelectTopic }: TopicSelectionPageProps) {
  const [query, setQuery] = useState("");
  const filteredTopics = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return topics;
    }
    return topics.filter((topic) =>
      `${topic.name} ${topic.description}`.toLowerCase().includes(normalizedQuery)
    );
  }, [query, topics]);

  return (
    <main className="app-shell">
      <div className="selection-topbar">
        <section className="selection-header">
          <p className="section-kicker">Company knowledge</p>
          <h1>What do you need help with?</h1>
        </section>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
      <div className="topic-search">
        <Search size={18} aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter topics"
          aria-label="Filter topics"
        />
      </div>
      <TopicGrid topics={filteredTopics} onSelectTopic={onSelectTopic} />
    </main>
  );
}
