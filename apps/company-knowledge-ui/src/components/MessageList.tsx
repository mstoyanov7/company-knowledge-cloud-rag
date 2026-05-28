import { useEffect, useRef } from "react";

import type { Topic } from "../api/topics";
import type { ChatMessage as ChatMessageModel } from "../state/conversations";
import { ChatMessage } from "./ChatMessage";
import { SuggestedQuestions } from "./SuggestedQuestions";

type MessageListProps = {
  topic: Topic;
  messages: ChatMessageModel[];
  onSelectQuestion: (question: string) => void;
};

export function MessageList({ topic, messages, onSelectQuestion }: MessageListProps) {
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, messages[messages.length - 1]?.status]);

  if (messages.length === 0) {
    return (
      <div className="chat-empty">
        <h2>Start a chat about {topic.name}</h2>
        <p>{topic.description}</p>
        <SuggestedQuestions questions={topic.suggested_questions} onSelectQuestion={onSelectQuestion} compact />
      </div>
    );
  }

  const lastDoneAssistantId = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && message.status === "done")?.id;

  return (
    <div className="message-list" aria-live="polite">
      {messages.map((message) => (
        <ChatMessage
          key={message.id}
          message={message}
          followUpQuestions={message.id === lastDoneAssistantId ? topic.suggested_questions : []}
          onSelectQuestion={onSelectQuestion}
        />
      ))}
      <div ref={scrollAnchorRef} />
    </div>
  );
}
