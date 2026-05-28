import { MessageSquare, Trash2 } from "lucide-react";

import type { Conversation } from "../state/conversations";

type ConversationListProps = {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
};

export function ConversationList({
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation
}: ConversationListProps) {
  if (conversations.length === 0) {
    return <p className="sidebar-empty">No chats match this topic.</p>;
  }

  return (
    <div className="conversation-list__items">
      {conversations.map((conversation) => (
        <div
          key={conversation.id}
          className={conversation.id === activeConversationId ? "conversation-item is-active" : "conversation-item"}
        >
          <button type="button" onClick={() => onSelectConversation(conversation.id)}>
            <MessageSquare size={16} aria-hidden="true" />
            <span>{conversation.title}</span>
            <small>{conversation.messages.filter((message) => message.role === "user").length} messages</small>
          </button>
          <button
            className="conversation-delete"
            type="button"
            onClick={() => onDeleteConversation(conversation.id)}
            aria-label={`Delete ${conversation.title}`}
          >
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}
