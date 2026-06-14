import { Check, Filter, Layers, Plus, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Citation, ConversationTurn } from "../api/answers";
import { streamTopicQuestion, type ClarificationOption } from "../api/answers";
import type { UiSettings } from "../api/admin";
import type { UserProfile } from "../api/auth";
import type { DocumentSummary } from "../api/documents";
import type { NotebookPage } from "../api/notebooks";
import type { Topic } from "../api/topics";
import {
  addAssistantPlaceholder,
  addUserMessage,
  conversationsForTopic,
  createConversation,
  deleteConversation,
  failAssistantMessage,
  loadConversations,
  resolveClarificationMessage,
  saveConversations,
  updateAssistantMessage,
  upsertConversation,
  type ChatMessage as ChatMessageModel,
  type Conversation
} from "../state/conversations";
import { isPinned, loadPins, savePins, togglePin, type PinnedItem } from "../state/pins";
import type { AccentHue, Density, Prefs } from "../state/prefs";
import type { Theme } from "../state/theme";
import { AdminPanel } from "./AdminPanel";
import { ChatComposer } from "./ChatComposer";
import { CommandPalette } from "./CommandPalette";
import { HomeView } from "./HomeView";
import { MessageList } from "./MessageList";
import { PreferencesPanel } from "./PreferencesPanel";
import { ProfileMenu } from "./ProfileMenu";
import { ProfileModal } from "./ProfileModal";
import { Rail } from "./Rail";
import {
  citationToPanelSource,
  documentToPanelSource,
  SourcePanel,
  type PanelSource,
  type PanelSourceAction
} from "./SourcePanel";
import { useToast } from "./ToastProvider";

type KnowledgeShellProps = {
  topics: Topic[];
  selectedTopic: Topic | null;
  theme: Theme;
  prefs: Prefs;
  user: UserProfile;
  uiSettings: UiSettings;
  onSelectTopic: (topicId: string) => void;
  onClearTopic: () => void;
  onToggleTheme: () => void;
  onSetTheme: (theme: Theme) => void;
  onSetDensity: (density: Density) => void;
  onSetAccent: (accent: AccentHue) => void;
  onSignOut: () => void;
  onUpdateUser: (user: UserProfile) => void;
  onTopicsChanged: () => void;
  onUiSettingsChanged: (settings: UiSettings) => void;
};

export function KnowledgeShell({
  topics,
  selectedTopic,
  theme,
  prefs,
  user,
  uiSettings,
  onSelectTopic,
  onClearTopic,
  onToggleTheme,
  onSetTheme,
  onSetDensity,
  onSetAccent,
  onSignOut,
  onUpdateUser,
  onTopicsChanged,
  onUiSettingsChanged
}: KnowledgeShellProps) {
  const { toast } = useToast();
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [panelSource, setPanelSource] = useState<PanelSource | null>(null);
  const [pins, setPins] = useState<PinnedItem[]>(() => loadPins());
  const [streamingId, setStreamingId] = useState<string | null>(null);

  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const [isScopeOpen, setIsScopeOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [isPrefsOpen, setIsPrefsOpen] = useState(false);
  const [isAdminOpen, setIsAdminOpen] = useState(false);
  const profileButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousTopicIdRef = useRef<string | null>(null);
  const skipNextAutoChatTopicIdRef = useRef<string | null>(null);
  const activeRequestRef = useRef<{
    id: string;
    controller: AbortController;
    conversationId: string;
    messageId: string;
    partialAnswer: string;
  } | null>(null);

  useEffect(() => {
    return () => {
      activeRequestRef.current?.controller.abort();
      activeRequestRef.current = null;
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setIsPaletteOpen((current) => !current);
        return;
      }
      if (event.key === "Escape" && !isPaletteOpen && panelSource) {
        setPanelSource(null);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isPaletteOpen, panelSource]);

  const topicConversations = useMemo(
    () => (selectedTopic ? conversationsForTopic(conversations, selectedTopic.id) : []),
    [conversations, selectedTopic]
  );

  const activeConversation = useMemo(() => {
    if (!selectedTopic) {
      return null;
    }
    if (activeConversationId) {
      const existing = conversations.find((conversation) => conversation.id === activeConversationId);
      if (existing?.topicId === selectedTopic.id) {
        return existing;
      }
    }
    return topicConversations[0] || null;
  }, [activeConversationId, conversations, selectedTopic, topicConversations]);

  useEffect(() => {
    if (!selectedTopic) {
      previousTopicIdRef.current = null;
      skipNextAutoChatTopicIdRef.current = null;
      return;
    }
    if (previousTopicIdRef.current !== selectedTopic.id) {
      previousTopicIdRef.current = selectedTopic.id;
      if (skipNextAutoChatTopicIdRef.current === selectedTopic.id) {
        skipNextAutoChatTopicIdRef.current = null;
        return;
      }
      const latest = loadConversations();
      const created = createConversation(selectedTopic.id);
      persist(upsertConversation(latest, created));
      setActiveConversationId(created.id);
      setPanelSource(null);
      return;
    }
    if (!activeConversation && topicConversations.length === 0) {
      const created = createConversation(selectedTopic.id);
      persist(upsertConversation(conversations, created));
      setActiveConversationId(created.id);
      return;
    }
    if (activeConversation && activeConversation.id !== activeConversationId) {
      setActiveConversationId(activeConversation.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConversation, activeConversationId, selectedTopic, topicConversations.length]);

  function persist(nextConversations: Conversation[]) {
    setConversations(nextConversations);
    saveConversations(nextConversations);
  }

  function persistPins(next: PinnedItem[]) {
    setPins(next);
    savePins(next);
  }

  function startConversation() {
    if (!selectedTopic) {
      return;
    }
    const created = createConversation(selectedTopic.id);
    persist(upsertConversation(conversations, created));
    setActiveConversationId(created.id);
    setPanelSource(null);
  }

  function removeConversation(conversationId: string) {
    if (!selectedTopic) {
      return;
    }
    const nextConversations = deleteConversation(conversations, conversationId);
    persist(nextConversations);
    if (conversationId === activeConversationId) {
      const nextActive = conversationsForTopic(nextConversations, selectedTopic.id)[0] || null;
      if (nextActive) {
        setActiveConversationId(nextActive.id);
      } else {
        const created = createConversation(selectedTopic.id);
        persist(upsertConversation(nextConversations, created));
        setActiveConversationId(created.id);
      }
    }
  }

  function askQuestion(question: string) {
    if (selectedTopic) {
      askInTopic(selectedTopic, question);
    }
  }

  function askInTopic(
    topic: Topic,
    question: string,
    options: { focusSourceItemIds?: string[]; displayText?: string } = {}
  ) {
    // Read the freshest conversations so this works even right after a topic
    // switch (when `activeConversation` from props is still stale).
    const current = loadConversations();
    const baseConversation = conversationsForTopic(current, topic.id)[0] || createConversation(topic.id);
    const history = conversationHistory(baseConversation);
    // `displayText` is what the user sees in their bubble (e.g. the topic they
    // picked); `question` is what the backend answers (the original question).
    const withUser = addUserMessage(baseConversation, options.displayText ?? question);
    const withAssistant = addAssistantPlaceholder(withUser.conversation, question);
    const pendingConversation = withAssistant.conversation;
    const pendingConversations = upsertConversation(current, pendingConversation);

    persist(pendingConversations);
    setActiveConversationId(pendingConversation.id);
    setIsSubmitting(true);
    setStreamingId(withAssistant.messageId);

    let streamedAnswer = "";
    const controller = new AbortController();
    const requestId = `${withAssistant.messageId}-${Date.now()}`;
    activeRequestRef.current = {
      id: requestId,
      controller,
      conversationId: pendingConversation.id,
      messageId: withAssistant.messageId,
      partialAnswer: ""
    };
    streamTopicQuestion(
      {
        topic_id: topic.id,
        conversation_id: pendingConversation.id,
        answer_depth: "detailed",
        question,
        history,
        ...(options.focusSourceItemIds?.length
          ? { focus_source_item_ids: options.focusSourceItemIds }
          : {})
      },
      {
        onDelta: (text) => {
          if (!isActiveRequest(requestId)) {
            return;
          }
          streamedAnswer += text;
          if (activeRequestRef.current?.id === requestId) {
            activeRequestRef.current.partialAnswer = streamedAnswer;
          }
          const latest = loadConversations();
          const latestConversation =
            latest.find((conversation) => conversation.id === pendingConversation.id) || pendingConversation;
          persist(
            upsertConversation(
              latest,
              updateAssistantMessage(latestConversation, withAssistant.messageId, {
                content: streamedAnswer,
                status: "loading"
              })
            )
          );
        }
      },
      { signal: controller.signal }
    )
      .then((response) => {
        if (!isActiveRequest(requestId)) {
          return;
        }
        const latest = loadConversations();
        const latestConversation =
          latest.find((conversation) => conversation.id === pendingConversation.id) || pendingConversation;
        persist(
          upsertConversation(
            latest,
            updateAssistantMessage(latestConversation, withAssistant.messageId, {
              content: response.answer,
              citations: response.citations,
              downloads: response.downloads || [],
              metadata: response.metadata,
              status: "done",
              clarification: response.clarification ?? null,
              clarificationResolved: false
            })
          )
        );
        setStreamingId(withAssistant.messageId);
      })
      .catch((error: Error) => {
        if (!isActiveRequest(requestId)) {
          return;
        }
        if (isAbortError(error)) {
          markRequestStopped(pendingConversation.id, withAssistant.messageId, streamedAnswer);
          return;
        }
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
        if (isActiveRequest(requestId)) {
          activeRequestRef.current = null;
          setIsSubmitting(false);
          window.setTimeout(() => setStreamingId(null), 250);
        }
      });
  }

  function stopAnswer() {
    const active = activeRequestRef.current;
    if (!active) {
      return;
    }
    active.controller.abort();
    markRequestStopped(active.conversationId, active.messageId, active.partialAnswer);
    activeRequestRef.current = null;
    setIsSubmitting(false);
    setStreamingId(null);
  }

  function markRequestStopped(conversationId: string, messageId: string, partialAnswer = "") {
    const latest = loadConversations();
    const latestConversation = latest.find((conversation) => conversation.id === conversationId);
    if (!latestConversation) {
      return;
    }
    persist(
      upsertConversation(
        latest,
        updateAssistantMessage(latestConversation, messageId, {
          content: partialAnswer.trim() || "Answer stopped.",
          status: "done",
          citations: [],
          downloads: [],
          clarification: null,
          clarificationResolved: false
        })
      )
    );
  }

  function isActiveRequest(requestId: string): boolean {
    return activeRequestRef.current?.id === requestId;
  }

  function resolveClarification(message: ChatMessageModel, option: ClarificationOption) {
    if (!selectedTopic || !message.clarification) {
      return;
    }
    // Disable the picker on the asked message, then re-ask the original question
    // restricted to the page the user chose.
    const current = loadConversations();
    const owning = current.find((conversation) =>
      conversation.messages.some((item) => item.id === message.id)
    );
    if (owning) {
      persist(upsertConversation(current, resolveClarificationMessage(owning, message.id)));
    }
    askInTopic(selectedTopic, message.clarification.original_question, {
      focusSourceItemIds: [option.source_item_id],
      displayText: option.title
    });
  }

  function selectConversation(conversationId: string) {
    setActiveConversationId(conversationId);
    setPanelSource(null);
  }

  function openCitation(citation: Citation) {
    setPanelSource(citationToPanelSource(citation));
  }

  function openDocumentSource(document: NotebookPage | DocumentSummary) {
    const topic = preferredTopicForSource(document);
    const panel = documentToPanelSource(document);
    setPanelSource({
      ...panel,
      actions: topic ? sourceActionsForDocument(document, topic.id, topic.name) : []
    });
  }

  function preferredTopicForSource(document: NotebookPage | DocumentSummary): Topic | null {
    const topicIds = Array.isArray(document.metadata?.topic_ids)
      ? document.metadata.topic_ids.map((value) => String(value))
      : [];
    const classifiedTopic = topicIds
      .map((topicId) => topics.find((candidate) => candidate.id === topicId))
      .find((topic): topic is Topic => Boolean(topic));
    return classifiedTopic || selectedTopic || null;
  }

  function sourceActionsForDocument(
    document: NotebookPage | DocumentSummary,
    topicId: string,
    topicName: string
  ): PanelSourceAction[] {
    const actions: PanelSourceAction[] = [
      {
        label: `Ask ${topicName} about this page`,
        question: `Summarize the key points from "${document.title}".`,
        topicId
      }
    ];
    const sectionName = sectionNameForSource(document);
    if (sectionName) {
      actions.push({
        label: `Ask ${topicName} about this section`,
        question: `What should I know about the "${sectionName}" section?`,
        topicId
      });
    }
    return actions;
  }

  function askFromSource(action: PanelSourceAction) {
    const topic = topics.find((candidate) => candidate.id === action.topicId);
    if (!topic) {
      toast("No matching topic found for this source.", "err");
      return;
    }
    if (topic.id !== selectedTopic?.id) {
      skipNextAutoChatTopicIdRef.current = topic.id;
      onSelectTopic(topic.id);
    }
    setPanelSource(null);
    askInTopic(topic, action.question);
  }

  function toggleConversationPin(conversation: Conversation) {
    const item: PinnedItem = { id: conversation.id, title: conversation.title, topicId: conversation.topicId };
    const next = togglePin(pins, item);
    persistPins(next);
    toast(isPinned(pins, conversation.id) ? "Unpinned chat." : "Pinned chat.", "ok");
  }

  function openPinnedConversation(item: PinnedItem) {
    const conversation = conversations.find((candidate) => candidate.id === item.id);
    if (!conversation) {
      persistPins(pins.filter((pin) => pin.id !== item.id));
      toast("Pinned chat no longer exists.", "err");
      return;
    }
    if (conversation.topicId !== selectedTopic?.id) {
      skipNextAutoChatTopicIdRef.current = conversation.topicId;
      onSelectTopic(conversation.topicId);
    }
    setActiveConversationId(conversation.id);
    setPanelSource(null);
  }

  function unpinPinnedConversation(item: PinnedItem) {
    persistPins(pins.filter((pin) => pin.id !== item.id));
    toast("Unpinned chat.", "ok");
  }

  function askSuggestedQuestion(item: { question: string; topicId: string }) {
    const topic = topics.find((candidate) => candidate.id === item.topicId);
    if (!topic) {
      return;
    }
    if (topic.id !== selectedTopic?.id) {
      skipNextAutoChatTopicIdRef.current = topic.id;
      onSelectTopic(topic.id);
    }
    askInTopic(topic, item.question);
  }

  const messages = activeConversation?.messages || [];
  const topbarTitle = selectedTopic ? activeConversation?.title || selectedTopic.name : "Home";

  return (
    <div className="app" data-source={panelSource ? "open" : "closed"}>
      <Rail
        topics={topics}
        selectedTopicId={selectedTopic?.id || null}
        conversations={topicConversations}
        activeConversationId={activeConversation?.id || null}
        pins={pins}
        user={user}
        uiSettings={uiSettings}
        onSelectTopic={onSelectTopic}
        onSelectConversation={selectConversation}
        onDeleteConversation={removeConversation}
        onTogglePin={toggleConversationPin}
        onOpenPinnedConversation={openPinnedConversation}
        onUnpinPinnedConversation={unpinPinnedConversation}
        onOpenSearch={() => setIsPaletteOpen(true)}
        isProfileMenuOpen={isProfileMenuOpen}
        profileButtonRef={profileButtonRef}
        onOpenProfile={() => setIsProfileMenuOpen((current) => !current)}
      />

      <main className="center">
        <div className="topbar">
          <div className="topbar__title">
            <h1>{topbarTitle}</h1>
          </div>
          <div className="topbar__spacer" />
          {selectedTopic ? (
            <button className="btn btn--ghost btn--sm" type="button" onClick={startConversation}>
              <Plus size={14} aria-hidden="true" /> New chat
            </button>
          ) : null}
        </div>

        <div className="thread scroll">
          {selectedTopic ? (
            <div className="thread__inner">
              <MessageList
                topic={selectedTopic}
                messages={messages}
                streamingId={streamingId}
                onSelectQuestion={askQuestion}
                onOpenSource={openCitation}
                onSelectClarification={resolveClarification}
              />
            </div>
          ) : (
            <HomeView
              userName={user.name}
              topics={topics}
              onSelectTopic={onSelectTopic}
              onAsk={askSuggestedQuestion}
              onOpenDocument={openDocumentSource}
            />
          )}
        </div>

        {selectedTopic ? (
          <div className="composer-wrap">
            <div className="composer-inner">
              <div className="scopebar">
                <span className="scopebar__label">Scope</span>
                <span className="scope-chip">
                  <Filter size={12} aria-hidden="true" />
                  <span>{selectedTopic.name}</span>
                  <button
                    className="scope-chip__x"
                    type="button"
                    onClick={onClearTopic}
                    aria-label="Change topic"
                    title="Change topic"
                  >
                    <X size={13} aria-hidden="true" />
                  </button>
                </span>
              </div>
              <ChatComposer
                isSubmitting={isSubmitting}
                onSubmit={askQuestion}
                onStop={stopAnswer}
                placeholder={`Ask anything about ${selectedTopic.name}...`}
              />
              <div className="composer-scoperow">
                <button
                  className="scope-tool"
                  type="button"
                  onClick={() => setIsScopeOpen((current) => !current)}
                  aria-expanded={isScopeOpen}
                >
                  <Filter size={13} aria-hidden="true" /> Scope
                </button>
                {isScopeOpen ? (
                  <>
                    <div className="popover-scrim" onClick={() => setIsScopeOpen(false)} />
                    <div className="scope-menu">
                      <div className="scope-menu__h">Scope answers to a topic</div>
                      {topics.map((topic) => (
                        <button
                          key={topic.id}
                          className="scope-menu__item"
                          type="button"
                          onClick={() => {
                            onSelectTopic(topic.id);
                            setIsScopeOpen(false);
                          }}
                        >
                          <span className="scope-menu__ico">
                            <Layers size={14} aria-hidden="true" />
                          </span>
                          <span className="scope-menu__l">{topic.name}</span>
                          <span className="scope-menu__ck">
                            {topic.id === selectedTopic.id ? <Check size={14} aria-hidden="true" /> : null}
                          </span>
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </main>

      <SourcePanel source={panelSource} onClose={() => setPanelSource(null)} onAskSource={askFromSource} />

      <CommandPalette
        open={isPaletteOpen}
        topics={topics}
        conversations={topicConversations}
        selectedTopic={selectedTopic}
        onClose={() => setIsPaletteOpen(false)}
        onSelectTopic={onSelectTopic}
        onSelectConversation={selectConversation}
        onAsk={askQuestion}
        onGoHome={onClearTopic}
      />

      {isProfileMenuOpen ? (
        <ProfileMenu
          user={user}
          theme={theme}
          anchorRef={profileButtonRef}
          onClose={() => setIsProfileMenuOpen(false)}
          onOpenProfile={() => {
            setIsProfileMenuOpen(false);
            setIsProfileModalOpen(true);
          }}
          onToggleTheme={onToggleTheme}
          onOpenPreferences={() => {
            setIsProfileMenuOpen(false);
            setIsPrefsOpen(true);
          }}
          onOpenAdmin={() => {
            setIsProfileMenuOpen(false);
            setIsAdminOpen(true);
          }}
          onSignOut={() => {
            setIsProfileMenuOpen(false);
            onSignOut();
          }}
        />
      ) : null}

      {isProfileModalOpen ? (
        <ProfileModal
          user={user}
          onClose={() => setIsProfileModalOpen(false)}
          onSave={(nextUser) => {
            onUpdateUser(nextUser);
            setIsProfileModalOpen(false);
          }}
          onSignOut={() => {
            setIsProfileModalOpen(false);
            onSignOut();
          }}
        />
      ) : null}

      {isPrefsOpen ? (
        <PreferencesPanel
          theme={theme}
          prefs={prefs}
          onClose={() => setIsPrefsOpen(false)}
          onSetTheme={onSetTheme}
          onSetDensity={onSetDensity}
          onSetAccent={onSetAccent}
        />
      ) : null}

      {isAdminOpen ? (
        <AdminPanel
          currentUser={user}
          uiSettings={uiSettings}
          onClose={() => setIsAdminOpen(false)}
          onTopicsChanged={onTopicsChanged}
          onUiSettingsChanged={onUiSettingsChanged}
        />
      ) : null}
    </div>
  );
}

// Recent completed turns of the active chat, sent so the backend can resolve
// follow-up questions ("how do I run it?") against earlier context.
function conversationHistory(conversation: Conversation, maxTurns = 12): ConversationTurn[] {
  return conversation.messages
    .filter((message) => message.status !== "loading" && message.content.trim().length > 0)
    .slice(-maxTurns)
    .map((message) => ({ role: message.role, content: message.content }));
}

function sectionNameForSource(document: NotebookPage | DocumentSummary): string | null {
  const metadataSection = document.metadata?.section_name;
  if (typeof metadataSection === "string" && metadataSection.trim()) {
    return metadataSection.trim();
  }
  const sectionPath = document.section_path || "";
  const parts = sectionPath
    .split(/[/>]/)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : null;
}

function isAbortError(error: Error): boolean {
  return error.name === "AbortError";
}
