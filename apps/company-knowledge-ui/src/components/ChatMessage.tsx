import type { ChatMessage as ChatMessageModel } from "../state/conversations";
import { CitationList } from "./CitationList";
import { MarkdownAnswer } from "./MarkdownAnswer";
import { SuggestedQuestions } from "./SuggestedQuestions";

type ChatMessageProps = {
  message: ChatMessageModel;
  followUpQuestions?: string[];
  onSelectQuestion: (question: string) => void;
};

export function ChatMessage({ message, followUpQuestions = [], onSelectQuestion }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <article className={isUser ? "chat-message chat-message--user" : "chat-message chat-message--assistant"}>
      <div className="chat-message__avatar" aria-hidden="true">
        {isUser ? "You" : "AI"}
      </div>
      <div className="chat-message__content">
        <div className="message-bubble">
          {message.status === "loading" ? (
            <div className="typing-state" role="status">
              <span />
              <span />
              <span />
            </div>
          ) : isUser ? (
            <p>{message.content}</p>
          ) : message.status === "error" ? (
            <p className="message-error">{message.content}</p>
          ) : (
            <MarkdownAnswer answer={message.content} />
          )}
        </div>
        {!isUser && message.status === "done" ? <CitationList citations={message.citations || []} /> : null}
        {!isUser && message.status === "done" && followUpQuestions.length ? (
          <SuggestedQuestions questions={followUpQuestions} onSelectQuestion={onSelectQuestion} compact />
        ) : null}
      </div>
    </article>
  );
}
