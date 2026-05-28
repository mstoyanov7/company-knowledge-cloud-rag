import { MessageSquarePlus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { Topic } from "../api/topics";
import { filterConversations, type Conversation } from "../state/conversations";
import type { Theme } from "../state/theme";
import { ConversationList } from "./ConversationList";
import { ThemeToggle } from "./ThemeToggle";

type HistorySidebarProps = {
  topic: Topic;
  conversations: Conversation[];
  activeConversationId: string | null;
  theme: Theme;
  onToggleTheme: () => void;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (conversationId: string) => void;
};

export function HistorySidebar({
  topic,
  conversations,
  activeConversationId,
  theme,
  onToggleTheme,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation
}: HistorySidebarProps) {
  const [query, setQuery] = useState("");
  const visibleConversations = useMemo(
    () => filterConversations(conversations, query),
    [conversations, query]
  );

  return (
    <aside className="history-sidebar" aria-label="Conversation history">
      <div className="sidebar-brand">
        <strong>Knowledge Assistant</strong>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>

      <button className="new-conversation" type="button" onClick={onNewConversation}>
        <MessageSquarePlus size={17} aria-hidden="true" />
        <span>New chat</span>
      </button>

      <div className="history-sidebar__topic">
        <span>Current topic</span>
        <strong>{topic.name}</strong>
      </div>

      <label className="conversation-search">
        <Search size={16} aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search chats"
        />
      </label>

      <ConversationList
        conversations={visibleConversations}
        activeConversationId={activeConversationId}
        onSelectConversation={onSelectConversation}
        onDeleteConversation={onDeleteConversation}
      />
    </aside>
  );
}
