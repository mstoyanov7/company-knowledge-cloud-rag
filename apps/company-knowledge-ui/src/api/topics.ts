import { apiRequest } from "./client";

export type Topic = {
  id: string;
  name: string;
  description: string;
  icon?: string;
  suggested_questions: string[];
};

export function fetchTopics(): Promise<Topic[]> {
  return apiRequest<Topic[]>("/api/v1/topics");
}
