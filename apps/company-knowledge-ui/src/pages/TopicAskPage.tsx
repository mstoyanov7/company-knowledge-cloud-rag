import type { Topic } from "../api/topics";
import { TopicWorkspace } from "../components/TopicWorkspace";
import type { Theme } from "../state/theme";

type TopicAskPageProps = {
  topic: Topic;
  theme: Theme;
  onToggleTheme: () => void;
  onChangeTopic: () => void;
};

export function TopicAskPage({ topic, theme, onToggleTheme, onChangeTopic }: TopicAskPageProps) {
  return (
    <TopicWorkspace
      topic={topic}
      theme={theme}
      onToggleTheme={onToggleTheme}
      onChangeTopic={onChangeTopic}
    />
  );
}
