import { Home, MessageSquare, Search, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Topic } from "../api/topics";
import type { Conversation } from "../state/conversations";
import { getTopicIcon } from "./topicIcon";

type Command = {
  id: string;
  group: string;
  label: string;
  sub?: string;
  icon: React.ReactNode;
  run: () => void;
};

type CommandPaletteProps = {
  open: boolean;
  topics: Topic[];
  conversations: Conversation[];
  selectedTopic: Topic | null;
  onClose: () => void;
  onSelectTopic: (topicId: string) => void;
  onSelectConversation: (conversationId: string) => void;
  onAsk: (question: string) => void;
  onGoHome: () => void;
};

export function CommandPalette({
  open,
  topics,
  conversations,
  selectedTopic,
  onClose,
  onSelectTopic,
  onSelectConversation,
  onAsk,
  onGoHome
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      // Focus after the overlay paints.
      const id = window.setTimeout(() => inputRef.current?.focus(), 20);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const normalized = query.trim().toLowerCase();
    const items: Command[] = [];

    if (normalized && selectedTopic) {
      const q = query.trim();
      items.push({
        id: "ask",
        group: "Ask",
        label: `Ask ${selectedTopic.name}: “${q}”`,
        icon: <Sparkles size={15} aria-hidden="true" />,
        run: () => onAsk(q)
      });
    }

    items.push({
      id: "home",
      group: "Navigate",
      label: "Go to Home",
      icon: <Home size={15} aria-hidden="true" />,
      run: onGoHome
    });

    for (const topic of topics) {
      const Icon = getTopicIcon(topic.icon);
      items.push({
        id: `topic-${topic.id}`,
        group: "Topics",
        label: topic.name,
        sub: topic.description,
        icon: <Icon size={15} aria-hidden="true" />,
        run: () => onSelectTopic(topic.id)
      });
    }

    for (const conversation of conversations) {
      items.push({
        id: `conv-${conversation.id}`,
        group: "Recent chats",
        label: conversation.title,
        icon: <MessageSquare size={15} aria-hidden="true" />,
        run: () => onSelectConversation(conversation.id)
      });
    }

    if (!normalized) {
      return items;
    }
    return items.filter(
      (item) =>
        item.id === "ask" ||
        `${item.label} ${item.sub ?? ""}`.toLowerCase().includes(normalized)
    );
  }, [conversations, onAsk, onGoHome, onSelectConversation, onSelectTopic, query, selectedTopic, topics]);

  useEffect(() => {
    if (selected >= commands.length) {
      setSelected(commands.length > 0 ? commands.length - 1 : 0);
    }
  }, [commands.length, selected]);

  if (!open) {
    return null;
  }

  function runAt(index: number) {
    const command = commands[index];
    if (!command) {
      return;
    }
    onClose();
    command.run();
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelected((current) => Math.min(current + 1, commands.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelected((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      runAt(selected);
    } else if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  }

  let lastGroup = "";

  return (
    <div className="cmdk-overlay is-open" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="cmdk" role="dialog" aria-label="Command palette" aria-modal="true">
        <div className="cmdk__input">
          <Search size={17} aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search topics, jump to a chat, or ask a question…"
            autoComplete="off"
          />
          <span className="kbd">esc</span>
        </div>
        <div className="cmdk__list scroll" ref={listRef}>
          {commands.length === 0 ? (
            <div className="cmdk__grouph">No matches</div>
          ) : (
            commands.map((command, index) => {
              const header = command.group !== lastGroup ? command.group : null;
              lastGroup = command.group;
              return (
                <div key={command.id}>
                  {header ? <div className="cmdk__grouph">{header}</div> : null}
                  <div
                    className={index === selected ? "cmdk__item is-sel" : "cmdk__item"}
                    onMouseEnter={() => setSelected(index)}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      runAt(index);
                    }}
                  >
                    <span className="ci">{command.icon}</span>
                    <span className="cm">
                      <b>{command.label}</b>
                      {command.sub ? <span>{command.sub}</span> : null}
                    </span>
                    <span className="ck">↵</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
