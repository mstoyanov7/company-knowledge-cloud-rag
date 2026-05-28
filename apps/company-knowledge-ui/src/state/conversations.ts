import type { Citation } from "../api/answers";
import { safeParseJson, type StorageLike } from "./storage";

const CONVERSATION_STORAGE_KEY = "companyKnowledgeConversations.v1";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  createdAt: string;
  status?: "loading" | "done" | "error";
};

export type Conversation = {
  id: string;
  topicId: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
};

export function loadConversations(storage: StorageLike = window.localStorage): Conversation[] {
  const rawConversations = safeParseJson<unknown[]>(storage.getItem(CONVERSATION_STORAGE_KEY), []);
  return rawConversations.map(normalizeConversation).filter((conversation): conversation is Conversation => {
    return conversation !== null;
  });
}

export function saveConversations(
  conversations: Conversation[],
  storage: StorageLike = window.localStorage
): void {
  storage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(conversations));
}

export function createConversation(topicId: string, now = new Date()): Conversation {
  const timestamp = now.toISOString();
  return {
    id: `conv-${now.getTime()}-${Math.random().toString(16).slice(2, 8)}`,
    topicId,
    title: "New chat",
    messages: [],
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

export function titleFromQuestion(question: string): string {
  const cleaned = question.replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return "New chat";
  }
  return cleaned.length > 48 ? `${cleaned.slice(0, 45).trim()}...` : cleaned;
}

export function conversationsForTopic(conversations: Conversation[], topicId: string): Conversation[] {
  return conversations
    .filter((conversation) => conversation.topicId === topicId)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

export function filterConversations(conversations: Conversation[], query: string): Conversation[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return conversations;
  }
  return conversations.filter((conversation) => {
    return `${conversation.title} ${conversation.topicId}`.toLowerCase().includes(normalizedQuery);
  });
}

export function upsertConversation(conversations: Conversation[], conversation: Conversation): Conversation[] {
  const index = conversations.findIndex((item) => item.id === conversation.id);
  if (index === -1) {
    return [conversation, ...conversations];
  }
  return conversations.map((item) => (item.id === conversation.id ? conversation : item));
}

export function deleteConversation(conversations: Conversation[], conversationId: string): Conversation[] {
  return conversations.filter((conversation) => conversation.id !== conversationId);
}

export function addUserMessage(
  conversation: Conversation,
  content: string,
  now = new Date()
): { conversation: Conversation; messageId: string } {
  const timestamp = now.toISOString();
  const messageId = messageIdFor("user", now);
  const nextTitle = conversation.messages.length === 0 ? titleFromQuestion(content) : conversation.title;

  return {
    messageId,
    conversation: {
      ...conversation,
      title: nextTitle,
      updatedAt: timestamp,
      messages: [
        ...conversation.messages,
        {
          id: messageId,
          role: "user",
          content,
          createdAt: timestamp,
          status: "done"
        }
      ]
    }
  };
}

export function addAssistantPlaceholder(
  conversation: Conversation,
  now = new Date()
): { conversation: Conversation; messageId: string } {
  const timestamp = now.toISOString();
  const messageId = messageIdFor("assistant", now);

  return {
    messageId,
    conversation: {
      ...conversation,
      updatedAt: timestamp,
      messages: [
        ...conversation.messages,
        {
          id: messageId,
          role: "assistant",
          content: "",
          createdAt: timestamp,
          status: "loading"
        }
      ]
    }
  };
}

export function completeAssistantMessage(
  conversation: Conversation,
  messageId: string,
  content: string,
  citations: Citation[] = [],
  now = new Date()
): Conversation {
  return updateMessage(
    conversation,
    messageId,
    {
      content,
      citations,
      status: "done"
    },
    now
  );
}

export function failAssistantMessage(
  conversation: Conversation,
  messageId: string,
  error: string,
  now = new Date()
): Conversation {
  return updateMessage(
    conversation,
    messageId,
    {
      content: error,
      citations: [],
      status: "error"
    },
    now
  );
}

export function replaceConversationMessage(
  conversations: Conversation[],
  conversationId: string,
  update: (conversation: Conversation) => Conversation
): Conversation[] {
  return conversations.map((conversation) =>
    conversation.id === conversationId ? update(conversation) : conversation
  );
}

function updateMessage(
  conversation: Conversation,
  messageId: string,
  update: Partial<ChatMessage>,
  now: Date
): Conversation {
  return {
    ...conversation,
    updatedAt: now.toISOString(),
    messages: conversation.messages.map((message) =>
      message.id === messageId
        ? {
            ...message,
            ...update
          }
        : message
    )
  };
}

function messageIdFor(role: ChatMessage["role"], now: Date): string {
  return `msg-${role}-${now.getTime()}-${Math.random().toString(16).slice(2, 8)}`;
}

function normalizeConversation(value: unknown): Conversation | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const rawConversation = value as Partial<Conversation> & {
    messages?: unknown[];
  };
  if (!rawConversation.id || !rawConversation.topicId) {
    return null;
  }

  const createdAt = rawConversation.createdAt || new Date().toISOString();
  const messages = (rawConversation.messages || []).flatMap((message) =>
    normalizeMessage(message, createdAt)
  );

  return {
    id: String(rawConversation.id),
    topicId: String(rawConversation.topicId),
    title: rawConversation.title || titleFromFirstMessage(messages),
    messages,
    createdAt,
    updatedAt: rawConversation.updatedAt || createdAt
  };
}

function normalizeMessage(value: unknown, fallbackTimestamp: string): ChatMessage[] {
  if (!value || typeof value !== "object") {
    return [];
  }

  const rawMessage = value as Partial<ChatMessage> & {
    question?: string;
    response?: { answer?: string; citations?: Citation[] };
    error?: string;
  };

  if (rawMessage.role === "user" || rawMessage.role === "assistant") {
    return [
      {
        id: String(rawMessage.id || `msg-${rawMessage.role}-${Date.now()}`),
        role: rawMessage.role,
        content: String(rawMessage.content || ""),
        citations: rawMessage.citations || [],
        createdAt: rawMessage.createdAt || fallbackTimestamp,
        status: rawMessage.status || "done"
      }
    ];
  }

  if (rawMessage.question) {
    const userMessage: ChatMessage = {
      id: `${rawMessage.id || `legacy-${Date.now()}`}-user`,
      role: "user",
      content: rawMessage.question,
      createdAt: rawMessage.createdAt || fallbackTimestamp,
      status: "done"
    };
    const assistantMessage: ChatMessage = {
      id: `${rawMessage.id || `legacy-${Date.now()}`}-assistant`,
      role: "assistant",
      content: rawMessage.response?.answer || rawMessage.error || "",
      citations: rawMessage.response?.citations || [],
      createdAt: rawMessage.createdAt || fallbackTimestamp,
      status: rawMessage.error ? "error" : rawMessage.response ? "done" : "loading"
    };
    return [userMessage, assistantMessage];
  }

  return [];
}

function titleFromFirstMessage(messages: ChatMessage[]): string {
  return titleFromQuestion(messages.find((message) => message.role === "user")?.content || "");
}
