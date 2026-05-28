import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { submitTopicQuestion } from "../api/answers";
import type { Topic } from "../api/topics";
import {
  addAssistantPlaceholder,
  addUserMessage,
  completeAssistantMessage,
  conversationsForTopic,
  createConversation,
  deleteConversation,
  failAssistantMessage,
  loadConversations,
  saveConversations,
  upsertConversation,
  type Conversation
} from "../state/conversations";
import type { Theme } from "../state/theme";
import { ChatComposer } from "./ChatComposer";
import { HistorySidebar } from "./HistorySidebar";
import { MessageList } from "./MessageList";

type ChatWorkspaceProps = {
  topic: Topic;
  theme: Theme;
  onToggleTheme: () => void;
  onChangeTopic: () => void;
};

export function ChatWorkspace({ topic, theme, onToggleTheme, onChangeTopic }: ChatWorkspaceProps) {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const topicConversations = useMemo(
    () => conversationsForTopic(conversations, topic.id),
    [conversations, topic.id]
  );

  const activeConversation = useMemo(() => {
    if (activeConversationId) {
      const existing = conversations.find((conversation) => conversation.id === activeConversationId);
      if (existing?.topicId === topic.id) {
        return existing;
      }
    }
    return topicConversations[0] || null;
  }, [activeConversationId, conversations, topic.id, topicConversations]);

  useEffect(() => {
    if (!activeConversation && topicConversations.length === 0) {
      const created = createConversation(topic.id);
      persist(upsertConversation(conversations, created));
      setActiveConversationId(created.id);
      return;
    }

    if (activeConversation && activeConversation.id !== activeConversationId) {
      setActiveConversationId(activeConversation.id);
    }
  }, [activeConversation, activeConversationId, conversations, topic.id, topicConversations.length]);

  function persist(nextConversations: Conversation[]) {
    setConversations(nextConversations);
    saveConversations(nextConversations);
  }

  function startConversation() {
    const created = createConversation(topic.id);
    persist(upsertConversation(conversations, created));
    setActiveConversationId(created.id);
  }

  function removeConversation(conversationId: string) {
    const nextConversations = deleteConversation(conversations, conversationId);
    persist(nextConversations);
    if (conversationId === activeConversationId) {
      const nextActive = conversationsForTopic(nextConversations, topic.id)[0] || null;
      if (nextActive) {
        setActiveConversationId(nextActive.id);
      } else {
        const created = createConversation(topic.id);
        persist(upsertConversation(nextConversations, created));
        setActiveConversationId(created.id);
      }
    }
  }

  function askQuestion(question: string) {
    const baseConversation = activeConversation || createConversation(topic.id);
    const withUser = addUserMessage(baseConversation, question);
    const withAssistant = addAssistantPlaceholder(withUser.conversation);
    const pendingConversation = withAssistant.conversation;
    const pendingConversations = upsertConversation(conversations, pendingConversation);

    persist(pendingConversations);
    setActiveConversationId(pendingConversation.id);
    setIsSubmitting(true);

    submitTopicQuestion({
      topic_id: topic.id,
      conversation_id: pendingConversation.id,
      answer_depth: "detailed",
      question
    })
      .then((response) => {
        const latest = loadConversations();
        const latestConversation =
          latest.find((conversation) => conversation.id === pendingConversation.id) || pendingConversation;
        persist(
          upsertConversation(
            latest,
            completeAssistantMessage(
              latestConversation,
              withAssistant.messageId,
              response.answer,
              response.citations
            )
          )
        );
      })
      .catch((error: Error) => {
        const latest = loadConversations();
        const latestConversation =
          latest.find((conversation) => conversation.id === pendingConversation.id) || pendingConversation;
        persist(
          upsertConversation(
            latest,
            failAssistantMessage(latestConversation, withAssistant.messageId, error.message)
          )
        );
      })
      .finally(() => {
        setIsSubmitting(false);
      });
  }

  return (
    <main className="chat-shell">
      <HistorySidebar
        topic={topic}
        conversations={topicConversations}
        activeConversationId={activeConversation?.id || null}
        theme={theme}
        onToggleTheme={onToggleTheme}
        onSelectConversation={setActiveConversationId}
        onNewConversation={startConversation}
        onDeleteConversation={removeConversation}
      />

      <section className="chat-main">
        <header className="chat-header">
          <button className="secondary-action" type="button" onClick={onChangeTopic}>
            <ArrowLeft size={18} aria-hidden="true" />
            <span>Change topic</span>
          </button>
          <div className="chat-header__topic">
            <span>Selected topic</span>
            <h1>{topic.name}</h1>
            <p>{topic.description}</p>
          </div>
        </header>

        <div className="chat-scroll">
          <MessageList topic={topic} messages={activeConversation?.messages || []} onSelectQuestion={askQuestion} />
        </div>

        <div className="composer-wrap">
          <ChatComposer isSubmitting={isSubmitting} onSubmit={askQuestion} />
          <p>Ctrl+Enter to send. Enter adds a new line.</p>
        </div>
      </section>
    </main>
  );
}
