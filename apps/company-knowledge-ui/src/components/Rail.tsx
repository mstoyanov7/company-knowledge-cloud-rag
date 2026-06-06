import {
  Layers,
  MessageSquare,
  Pin,
  Search,
  Trash2
} from "lucide-react";
import { type RefObject } from "react";

import type { UserProfile } from "../api/auth";
import type { UiSettings } from "../api/admin";
import type { Topic } from "../api/topics";
import type { Conversation } from "../state/conversations";
import { isPinned, type PinnedItem } from "../state/pins";
import { initialsOf } from "../utils/user";
import { getTopicIcon } from "./topicIcon";

type RailProps = {
  topics: Topic[];
  selectedTopicId: string | null;
  conversations: Conversation[];
  activeConversationId: string | null;
  pins: PinnedItem[];
  user: UserProfile;
  uiSettings: UiSettings;
  onSelectTopic: (topicId: string) => void;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
  onTogglePin: (conversation: Conversation) => void;
  onAskPinned: (item: PinnedItem) => void;
  onOpenSearch: () => void;
  isProfileMenuOpen: boolean;
  profileButtonRef: RefObject<HTMLButtonElement | null>;
  onOpenProfile: () => void;
};

export function Rail({
  topics,
  selectedTopicId,
  conversations,
  activeConversationId,
  pins,
  user,
  uiSettings,
  onSelectTopic,
  onSelectConversation,
  onDeleteConversation,
  onTogglePin,
  onAskPinned,
  onOpenSearch,
  isProfileMenuOpen,
  profileButtonRef,
  onOpenProfile
}: RailProps) {
  return (
    <aside className="rail">
      <div className="rail__top">
        <div className="brand">
          <div className="brand__mark">
            {uiSettings.logo_url ? (
              <img src={uiSettings.logo_url} alt="" />
            ) : uiSettings.logo_text ? (
              <b>{uiSettings.logo_text.slice(0, 3).toUpperCase()}</b>
            ) : (
              <Layers size={15} aria-hidden="true" />
            )}
          </div>
          <div>
            <div className="brand__name">{uiSettings.app_name}</div>
            <div className="brand__sub">{uiSettings.app_subtitle}</div>
          </div>
        </div>
      </div>

      <button className="rail__search" type="button" onClick={onOpenSearch}>
        <Search size={14} aria-hidden="true" />
        <span>Search or ask...</span>
        <span className="kbd">Ctrl K</span>
      </button>

      <div className="rail__scroll scroll">
        <div className="rail__sectlabel">Knowledge topics</div>
        <div className="topic-list">
          {topics.map((topic) => {
            const Icon = getTopicIcon(topic.icon);
            return (
              <button
                key={topic.id}
                type="button"
                className={topic.id === selectedTopicId ? "topic-row is-active" : "topic-row"}
                onClick={() => onSelectTopic(topic.id)}
              >
                <span className="topic-row__ico">
                  <Icon size={15} aria-hidden="true" />
                </span>
                <span className="topic-row__label">{topic.name}</span>
              </button>
            );
          })}
        </div>

        {pins.length > 0 ? (
          <>
            <div className="rail__sectlabel">Pinned answers</div>
            {pins.map((pin) => (
              <div key={pin.id} className="li-wrap">
                <button type="button" className="li" onClick={() => onAskPinned(pin)}>
                  <span className="li__ico">
                    <Pin size={13} aria-hidden="true" />
                  </span>
                  <span className="li__label">{pin.question}</span>
                </button>
              </div>
            ))}
          </>
        ) : null}

        <div className="rail__sectlabel">Recent</div>
        {conversations.length === 0 ? (
          <div className="rail__empty">
            {selectedTopicId ? "No chats in this topic yet." : "Pick a topic to start a chat."}
          </div>
        ) : (
          conversations.map((conversation) => (
            <div key={conversation.id} className="li-wrap">
              <button
                type="button"
                className={conversation.id === activeConversationId ? "li is-active" : "li"}
                onClick={() => onSelectConversation(conversation.id)}
              >
                <span className="li__ico">
                  <MessageSquare size={13} aria-hidden="true" />
                </span>
                <span className="li__label">{conversation.title}</span>
              </button>
              <button
                type="button"
                className={isPinned(pins, conversation.id) ? "li__pin is-pinned" : "li__pin"}
                onClick={() => onTogglePin(conversation)}
                aria-label={isPinned(pins, conversation.id) ? "Unpin" : "Pin"}
                title={isPinned(pins, conversation.id) ? "Unpin" : "Pin"}
              >
                <Pin size={12} aria-hidden="true" />
              </button>
              <button
                type="button"
                className="li__del"
                onClick={() => onDeleteConversation(conversation.id)}
                aria-label={`Delete ${conversation.title}`}
              >
                <Trash2 size={13} aria-hidden="true" />
              </button>
            </div>
          ))
        )}
      </div>

      <div className="rail__foot">
        <button
          ref={profileButtonRef}
          className="profile-btn"
          type="button"
          onClick={onOpenProfile}
          aria-haspopup="menu"
          aria-expanded={isProfileMenuOpen}
        >
          <span className="avatar-sm">{initialsOf(user.name)}</span>
          <span className="who">
            <b>{user.name}</b>
            <span>{user.role || user.dept || user.roles[0] || "Employee"}</span>
          </span>
        </button>
      </div>
    </aside>
  );
}

