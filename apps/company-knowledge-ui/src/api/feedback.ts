import { apiRequest } from "./client";

export type FeedbackRequest = {
  response_id: string;
  conversation_id?: string | null;
  rating?: "up" | "down" | null;
  flag_gap: boolean;
  comment?: string | null;
  question: string;
  topic_id?: string | null;
};

export type FeedbackResponse = FeedbackRequest & {
  id: string;
  user_id: string;
  tenant_id: string;
  created_at_utc: string;
};

export function submitFeedback(request: FeedbackRequest): Promise<FeedbackResponse> {
  return apiRequest<FeedbackResponse>("/api/v1/feedback", { method: "POST", body: request });
}

