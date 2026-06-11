import { apiRequest } from "./client";

export type Topic = {
  id: string;
  name: string;
  description: string;
  icon?: string;
  suggested_questions: string[];
};

export type TopicAdmin = Topic & {
  acl_tags: string[];
  source_filters: string[];
  retrieval_tags: string[];
  enabled: boolean;
  created_at_utc: string;
  updated_at_utc: string;
  updated_by_user_id?: string | null;
};

export type TopicCreateRequest = {
  id: string;
  name: string;
  description: string;
  icon?: string | null;
  acl_tags: string[];
  retrieval_tags: string[];
  suggested_questions: string[];
  enabled: boolean;
};

export type TopicUpdateRequest = Partial<Omit<TopicCreateRequest, "id">>;

export function fetchTopics(): Promise<Topic[]> {
  return apiRequest<Topic[]>("/api/v1/topics");
}
