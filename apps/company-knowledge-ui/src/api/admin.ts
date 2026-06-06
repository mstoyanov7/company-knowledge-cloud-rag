import { apiRequest } from "./client";
import type { TopicAdmin, TopicCreateRequest, TopicUpdateRequest } from "./topics";
import type { UserProfile } from "./auth";

export type AdminUserUpdate = {
  name?: string;
  status?: UserProfile["status"];
  app_role?: UserProfile["app_role"];
  role?: string | null;
  dept?: string | null;
  acl_tags?: string[];
};

export type UiSettings = {
  app_name: string;
  app_subtitle: string;
  accent_hue: number;
  logo_url?: string | null;
  logo_text?: string | null;
  updated_at_utc?: string;
  updated_by_user_id?: string | null;
};

export type UiSettingsUpdate = Partial<Pick<UiSettings, "accent_hue" | "app_name" | "app_subtitle" | "logo_text" | "logo_url">>;

export function fetchUiSettings(): Promise<UiSettings> {
  return apiRequest<UiSettings>("/api/v1/ui-settings");
}

export function fetchAdminUsers(): Promise<UserProfile[]> {
  return apiRequest<UserProfile[]>("/api/v1/admin/users");
}

export function updateAdminUser(userId: string, request: AdminUserUpdate): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/api/v1/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: request
  });
}

export function approveUser(userId: string): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/api/v1/admin/users/${encodeURIComponent(userId)}/approve`, { method: "POST" });
}

export function rejectUser(userId: string): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/api/v1/admin/users/${encodeURIComponent(userId)}/reject`, { method: "POST" });
}

export function suspendUser(userId: string): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/api/v1/admin/users/${encodeURIComponent(userId)}/suspend`, { method: "POST" });
}

export function fetchAdminTopics(): Promise<TopicAdmin[]> {
  return apiRequest<TopicAdmin[]>("/api/v1/admin/topics");
}

export function createAdminTopic(request: TopicCreateRequest): Promise<TopicAdmin> {
  return apiRequest<TopicAdmin>("/api/v1/admin/topics", { method: "POST", body: request });
}

export function updateAdminTopic(topicId: string, request: TopicUpdateRequest): Promise<TopicAdmin> {
  return apiRequest<TopicAdmin>(`/api/v1/admin/topics/${encodeURIComponent(topicId)}`, {
    method: "PATCH",
    body: request
  });
}

export function disableAdminTopic(topicId: string): Promise<TopicAdmin> {
  return apiRequest<TopicAdmin>(`/api/v1/admin/topics/${encodeURIComponent(topicId)}`, { method: "DELETE" });
}

export function updateUiSettings(request: UiSettingsUpdate): Promise<UiSettings> {
  return apiRequest<UiSettings>("/api/v1/admin/ui-settings", { method: "PATCH", body: request });
}
