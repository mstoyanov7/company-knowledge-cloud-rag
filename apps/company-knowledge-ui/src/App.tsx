import { useEffect, useMemo, useState } from "react";

import { fetchTopics, type Topic } from "./api/topics";
import { ErrorState } from "./components/ErrorState";
import { LoadingState } from "./components/LoadingState";
import { TopicAskPage } from "./pages/TopicAskPage";
import { TopicSelectionPage } from "./pages/TopicSelectionPage";
import { loadTheme, nextTheme, saveTheme, type Theme } from "./state/theme";

export default function App() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(() => loadTheme());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    saveTheme(theme);
  }, [theme]);

  useEffect(() => {
    let isCurrent = true;

    fetchTopics()
      .then((items) => {
        if (!isCurrent) {
          return;
        }
        setTopics(items);
        setError(null);
      })
      .catch((loadError: Error) => {
        if (isCurrent) {
          setError(loadError.message);
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  const selectedTopic = useMemo(
    () => topics.find((topic) => topic.id === selectedTopicId) || null,
    [selectedTopicId, topics]
  );

  if (isLoading) {
    return <LoadingState label="Loading knowledge topics" />;
  }

  if (error) {
    return (
      <main className="app-shell app-shell--centered">
        <ErrorState title="Topics are unavailable" message={error} />
      </main>
    );
  }

  if (selectedTopic) {
    return (
      <TopicAskPage
        topic={selectedTopic}
        theme={theme}
        onToggleTheme={() => setTheme((currentTheme) => nextTheme(currentTheme))}
        onChangeTopic={() => setSelectedTopicId(null)}
      />
    );
  }

  return (
    <TopicSelectionPage
      topics={topics}
      theme={theme}
      onToggleTheme={() => setTheme((currentTheme) => nextTheme(currentTheme))}
      onSelectTopic={setSelectedTopicId}
    />
  );
}
