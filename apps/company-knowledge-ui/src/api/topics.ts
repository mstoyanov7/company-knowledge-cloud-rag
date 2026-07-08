import { apiRequest } from "./client";

export type Topic = {
  id: string;
  name: string;
  description: string;
  icon?: string;
  suggested_questions: string[];
};

// Sentinel "topic" that searches across everything the user can access. It is
// not a real topic: when selected, the answer request is sent without a
// topic_id so the backend searches all accessible content (ACL still applies).
export const ALL_TOPICS_ID = "__all__";

export const ALL_TOPICS_TOPIC: Topic = {
  id: ALL_TOPICS_ID,
  name: "Everything",
  description: "Searches across all topics — not selecting a filter may increase answer time.",
  icon: "layers",
  suggested_questions: []
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
  retrieval_tags?: string[];
  suggested_questions: string[];
  enabled: boolean;
};

export type TopicUpdateRequest = Partial<Omit<TopicCreateRequest, "id">>;

export function fetchTopics(): Promise<Topic[]> {
  return apiRequest<Topic[]>("/api/v1/topics");
}
