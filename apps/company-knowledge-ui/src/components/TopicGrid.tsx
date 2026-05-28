import type { Topic } from "../api/topics";
import { EmptyState } from "./EmptyState";
import { TopicCard } from "./TopicCard";

type TopicGridProps = {
  topics: Topic[];
  onSelectTopic: (topicId: string) => void;
};

export function TopicGrid({ topics, onSelectTopic }: TopicGridProps) {
  if (topics.length === 0) {
    return <EmptyState title="No matching topics" message="Try another topic name." />;
  }

  return (
    <div className="topic-grid">
      {topics.map((topic) => (
        <TopicCard key={topic.id} topic={topic} onSelect={onSelectTopic} />
      ))}
    </div>
  );
}
