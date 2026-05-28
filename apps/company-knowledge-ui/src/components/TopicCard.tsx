import {
  ClipboardCheck,
  Download,
  LifeBuoy,
  Rocket,
  Shield,
  Users,
  Wallet,
  Wrench
} from "lucide-react";

import type { Topic } from "../api/topics";

type TopicCardProps = {
  topic: Topic;
  onSelect: (topicId: string) => void;
};

const iconMap = {
  "clipboard-check": ClipboardCheck,
  download: Download,
  "life-buoy": LifeBuoy,
  rocket: Rocket,
  shield: Shield,
  users: Users,
  wallet: Wallet,
  wrench: Wrench
};

export function TopicCard({ topic, onSelect }: TopicCardProps) {
  const Icon = iconMap[topic.icon as keyof typeof iconMap] || ClipboardCheck;

  return (
    <button className="topic-card" type="button" onClick={() => onSelect(topic.id)}>
      <span className="topic-card__icon" aria-hidden="true">
        <Icon size={22} strokeWidth={2} />
      </span>
      <span className="topic-card__content">
        <span className="topic-card__title">{topic.name}</span>
        <span className="topic-card__description">{topic.description}</span>
      </span>
    </button>
  );
}
