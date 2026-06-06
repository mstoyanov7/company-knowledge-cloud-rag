import { apiRequest, clearAuthToken, setAuthToken } from "./client";

export type UserProfile = {
  user_id: string;
  email: string;
  name: string;
  tenant_id: string;
  acl_tags: string[];
  groups: string[];
  roles: string[];
  role?: string | null;
  dept?: string | null;
  status: "pending" | "active" | "suspended" | "rejected";
  app_role: "user" | "system_admin";
  approved_by_user_id?: string | null;
  approved_at_utc?: string | null;
  last_login_at_utc?: string | null;
  created_at_utc: string;
  updated_at_utc?: string | null;
  updated_by_user_id?: string | null;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type RegisterRequest = {
  email: string;
  password: string;
  name: string;
  role?: string;
  dept?: string;
};

export type UserProfileUpdate = {
  name?: string;
  role?: string | null;
  dept?: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at_utc: string;
  user: UserProfile;
};

export type RegistrationResponse = {
  success: boolean;
  email: string;
  status: "pending" | "active" | "suspended" | "rejected";
  message: string;
};

export async function login(request: LoginRequest): Promise<AuthResponse> {
  const response = await apiRequest<AuthResponse>("/api/v1/auth/login", { method: "POST", body: request });
  setAuthToken(response.access_token);
  return response;
}

export async function register(request: RegisterRequest): Promise<RegistrationResponse> {
  return apiRequest<RegistrationResponse>("/api/v1/auth/register", { method: "POST", body: request });
}

export function fetchMe(): Promise<UserProfile> {
  return apiRequest<UserProfile>("/api/v1/auth/me");
}

export function updateMe(request: UserProfileUpdate): Promise<UserProfile> {
  return apiRequest<UserProfile>("/api/v1/auth/me", { method: "PATCH", body: request });
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<{ success: boolean }>("/api/v1/auth/logout", { method: "POST" });
  } finally {
    clearAuthToken();
  }
}

