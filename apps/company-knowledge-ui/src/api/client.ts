const apiBaseUrl = (import.meta.env.VITE_RAG_API_BASE_URL || "").replace(/\/$/, "");
const ragApiKey = import.meta.env.VITE_RAG_API_KEY || "";
const AUTH_TOKEN_KEY = "companyKnowledgeAuthToken.v1";

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
};

export function getAuthToken(): string {
  return authStorage()?.getItem(AUTH_TOKEN_KEY) || "";
}

export function setAuthToken(token: string): void {
  authStorage()?.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  authStorage()?.removeItem(AUTH_TOKEN_KEY);
}

export function apiUrl(path: string): string {
  return `${apiBaseUrl}${path}`;
}

export function apiHeaders({ json = false }: { json?: boolean } = {}): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json"
  };

  if (json) {
    headers["Content-Type"] = "application/json";
  }

  if (ragApiKey) {
    headers["X-RAG-API-Key"] = ragApiKey;
  }

  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = apiHeaders({ json: options.body !== undefined });

  const response = await fetch(apiUrl(path), {
    method: options.method || "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal
  });

  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export async function downloadApiFile(path: string, fileName?: string): Promise<void> {
  const response = await fetch(apiUrl(path), {
    method: "GET",
    headers: apiHeaders()
  });

  if (!response.ok) {
    throw new Error(await responseError(response));
  }

  const blob = await response.blob();
  const resolvedName = fileName || fileNameFromDisposition(response.headers.get("Content-Disposition")) || "download";
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = resolvedName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function isApiDownloadUrl(value: string): boolean {
  return /^\/api\/v1\/attachments\/[^/]+\/download(?:\?.*)?$/.test(value);
}

function authStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || response.statusText || "Request failed.";
  } catch {
    return response.statusText || "Request failed.";
  }
}

function fileNameFromDisposition(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(value);
  return match ? decodeURIComponent(match[1].replace(/"$/, "")) : null;
}
