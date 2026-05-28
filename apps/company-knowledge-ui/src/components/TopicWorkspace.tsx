import type { Topic } from "../api/topics";
import type { Theme } from "../state/theme";
import { ChatWorkspace } from "./ChatWorkspace";

type TopicWorkspaceProps = {
  topic: Topic;
  theme: Theme;
  onToggleTheme: () => void;
  onChangeTopic: () => void;
};

export function TopicWorkspace({ topic, theme, onToggleTheme, onChangeTopic }: TopicWorkspaceProps) {
  return (
    <ChatWorkspace topic={topic} theme={theme} onToggleTheme={onToggleTheme} onChangeTopic={onChangeTopic} />
  );
}
