import { apiHeaders, apiRequest, apiUrl } from "./client";

export type Citation = {
  index?: number;
  chunk_id?: string;
  source_item_id?: string;
  chunk_index?: number;
  title: string;
  source_system: string;
  source_url: string;
  source_container?: string;
  section_path?: string | null;
  last_modified_utc?: string;
  snippet?: string;
  last_edited_by?: string | null;
  client_url?: string | null;
  metadata?: Record<string, unknown>;
};

export type DownloadLink = {
  download_id: string;
  file_name: string;
  mime_type?: string | null;
  file_extension: string;
  size_bytes: number;
  readable: boolean;
  parent_source_item_id: string;
  parent_title: string;
  download_url: string;
  indexed_source_item_id?: string | null;
};

export type AnswerMetadata = {
  response_id: string;
  provider?: string;
  model?: string;
  retrieval_strategy?: string;
  retrieved_chunk_count?: number;
  source_systems?: string[];
  generated_at_utc?: string;
  duration_ms?: number;
  retrieval_latency_ms?: number;
  completion_latency_ms?: number;
  freshness_delay_ms?: number | null;
  citation_count?: number;
};

export type ClarificationOption = {
  source_item_id: string;
  title: string;
  section_path?: string | null;
  hint?: string;
};

export type Clarification = {
  prompt: string;
  options: ClarificationOption[];
  original_question: string;
};

export type AnswerResponse = {
  answer: string;
  citations: Citation[];
  downloads?: DownloadLink[];
  metadata: AnswerMetadata;
  suggested_questions?: string[];
  clarification?: Clarification | null;
};

export type ConversationTurn = {
  role: "user" | "assistant";
  content: string;
};

export type TopicAnswerRequest = {
  topic_id: string;
  conversation_id?: string;
  answer_depth?: "concise" | "normal" | "detailed";
  answer_style?: string;
  question: string;
  history?: ConversationTurn[];
  focus_source_item_ids?: string[];
};

type AnswerRequestOptions = {
  signal?: AbortSignal;
};

export function submitTopicQuestion(
  request: TopicAnswerRequest,
  options: AnswerRequestOptions = {}
): Promise<AnswerResponse> {
  return apiRequest<AnswerResponse>("/api/v1/answer", {
    method: "POST",
    body: request,
    signal: options.signal
  });
}

type StreamHandlers = {
  onDelta: (text: string) => void;
  onFinal?: (response: AnswerResponse) => void;
};

export async function streamTopicQuestion(
  request: TopicAnswerRequest,
  handlers: StreamHandlers,
  options: AnswerRequestOptions = {}
): Promise<AnswerResponse> {
  const response = await fetch(apiUrl("/api/v1/answer/stream"), {
    method: "POST",
    headers: apiHeaders({ json: true }),
    body: JSON.stringify(request),
    signal: options.signal
  });

  if (!response.ok) {
    throw new Error(await responseError(response));
  }

  if (!response.body) {
    const fallback = await submitTopicQuestion(request, { signal: options.signal });
    handlers.onDelta(fallback.answer);
    handlers.onFinal?.(fallback);
    return fallback;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: AnswerResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\n\n/);
    buffer = parts.pop() || "";
    for (const part of parts) {
      const event = parseEvent(part);
      if (!event) {
        continue;
      }
      if (event.event === "delta") {
        handlers.onDelta(String(event.data.text || ""));
      } else if (event.event === "final") {
        finalResponse = event.data as unknown as AnswerResponse;
        handlers.onFinal?.(finalResponse);
      } else if (event.event === "error") {
        throw new Error(String(event.data.detail || "Streaming answer failed."));
      }
    }
  }

  if (buffer.trim()) {
    const event = parseEvent(buffer);
    if (event?.event === "final") {
      finalResponse = event.data as unknown as AnswerResponse;
      handlers.onFinal?.(finalResponse);
    }
  }

  if (!finalResponse) {
    throw new Error("Streaming answer ended before final metadata arrived.");
  }
  return finalResponse;
}

function parseEvent(raw: string): { event: string; data: Record<string, unknown> } | null {
  const event = raw.match(/^event:\s*(.+)$/m)?.[1]?.trim();
  const data = raw.match(/^data:\s*(.+)$/m)?.[1]?.trim();
  if (!event || !data) {
    return null;
  }
  return { event, data: JSON.parse(data) as Record<string, unknown> };
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || response.statusText || "Request failed.";
  } catch {
    return response.statusText || "Request failed.";
  }
}
