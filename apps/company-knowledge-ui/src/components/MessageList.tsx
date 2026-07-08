import { useEffect, useRef } from "react";

import type { Citation, ClarificationOption } from "../api/answers";
import { ALL_TOPICS_ID, type Topic } from "../api/topics";
import type { ChatMessage as ChatMessageModel } from "../state/conversations";
import { ChatMessage } from "./ChatMessage";
import { SuggestedQuestions } from "./SuggestedQuestions";

type MessageListProps = {
  topic: Topic;
  messages: ChatMessageModel[];
  streamingId?: string | null;
  onSelectQuestion: (question: string) => void;
  onOpenSource: (citation: Citation) => void;
  onSelectClarification?: (message: ChatMessageModel, option: ClarificationOption) => void;
};

export function MessageList({
  topic,
  messages,
  streamingId,
  onSelectQuestion,
  onOpenSource,
  onSelectClarification
}: MessageListProps) {
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, messages[messages.length - 1]?.status]);

  if (messages.length === 0) {
    return (
      <div className="chat-empty">
        <h2>{topic.id === ALL_TOPICS_ID ? "Ask anything across all topics" : `Start a chat about ${topic.name}`}</h2>
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
          isStreaming={message.id === streamingId}
          followUpQuestions={message.id === lastDoneAssistantId ? topic.suggested_questions : []}
          onSelectQuestion={onSelectQuestion}
          onOpenSource={onOpenSource}
          onSelectClarification={onSelectClarification}
          onStreamTick={() => scrollAnchorRef.current?.scrollIntoView({ block: "end" })}
        />
      ))}
      <div ref={scrollAnchorRef} />
    </div>
  );
}
