import { apiRequest } from "./client";

export type TrendingQuestion = {
  question: string;
  topic_id?: string | null;
  count: number;
  unique_users?: number;
  last_asked_utc?: string | null;
};

export function fetchTrendingQuestions({ window = "7d", limit = 8 } = {}): Promise<TrendingQuestion[]> {
  return apiRequest<TrendingQuestion[]>(`/api/v1/trending?window=${encodeURIComponent(window)}&limit=${limit}`);
}

