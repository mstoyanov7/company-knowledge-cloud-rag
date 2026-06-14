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

export type OpsJob = {
  job_id: string;
  job_type: string;
  dedupe_key: string;
  payload: Record<string, unknown>;
  status: "pending" | "running" | "succeeded" | "failed" | "dead_letter";
  attempts: number;
  max_attempts: number;
  available_at_utc: string;
  locked_at_utc?: string | null;
  locked_by?: string | null;
  last_error?: string | null;
  created_at_utc: string;
  updated_at_utc: string;
  completed_at_utc?: string | null;
};

export type AdminSystemSettings = {
  llm_provider: string;
  llm_model: string;
  available_llm_models: string[];
  onenote_sync_interval_seconds: number;
  onenote_sync_daily_time: string;
  onenote_sync_timezone?: string;
  onenote_sync_paused: boolean;
  last_sync_job?: OpsJob | null;
  updated_at_utc?: string | null;
  updated_by_user_id?: string | null;
};

export type AdminSystemSettingsUpdate = {
  llm_model?: string;
  onenote_sync_interval_seconds?: number;
  onenote_sync_daily_time?: string;
  onenote_sync_paused?: boolean;
};

export type ForceSyncResponse = {
  job: OpsJob;
  created: boolean;
  settings: AdminSystemSettings;
};

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

export function activateUser(userId: string): Promise<UserProfile> {
  return updateAdminUser(userId, { status: "active" });
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

export function fetchAdminSystemSettings(): Promise<AdminSystemSettings> {
  return apiRequest<AdminSystemSettings>("/api/v1/admin/system-settings");
}

export function updateAdminSystemSettings(request: AdminSystemSettingsUpdate): Promise<AdminSystemSettings> {
  return apiRequest<AdminSystemSettings>("/api/v1/admin/system-settings", { method: "PATCH", body: request });
}

export function forceSystemSync(): Promise<ForceSyncResponse> {
  return apiRequest<ForceSyncResponse>("/api/v1/admin/system-sync/run", { method: "POST" });
}
