import { apiRequest } from "./client";

export type Citation = {
  title: string;
  source_system: string;
  source_url: string;
  section_path?: string | null;
  last_modified_utc?: string;
};

export type AnswerResponse = {
  answer: string;
  citations: Citation[];
  suggested_questions?: string[];
};

export type TopicAnswerRequest = {
  topic_id: string;
  conversation_id?: string;
  answer_depth?: "concise" | "normal" | "detailed";
  answer_style?: string;
  question: string;
};

export function submitTopicQuestion(request: TopicAnswerRequest): Promise<AnswerResponse> {
  return apiRequest<AnswerResponse>("/api/v1/answer", {
    method: "POST",
    body: request
  });
}
