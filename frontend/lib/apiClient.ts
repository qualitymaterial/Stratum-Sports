const TOKEN_KEY = "stratum_token";

let authToken = "";
let initializedToken = false;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function normalizeApiBase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const noTrailing = trimTrailingSlash(trimmed);
  return noTrailing.endsWith("/api/v1") ? noTrailing : `${noTrailing}/api/v1`;
}

function resolveApiBaseUrl(): string {
  const envValue = normalizeApiBase(
    process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.VITE_API_URL ||
      process.env.REACT_APP_API_URL ||
      "",
  );
  if (envValue) {
    return envValue;
  }

  if (isBrowser()) {
    const { protocol, hostname, origin } = window.location;
    const isLocal =
      hostname === "localhost" || hostname === "127.0.0.1" || protocol === "file:";
    if (isLocal) {
      return "http://localhost:8000/api/v1";
    }
    return `${trimTrailingSlash(origin)}/api/v1`;
  }

  return "http://localhost:8000/api/v1";
}

const API_BASE_URL = resolveApiBaseUrl();

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function setAuthToken(token: string): void {
  authToken = token.trim();
}

export function clearAuthToken(): void {
  authToken = "";
}

export function initializeAuthToken(): string {
  if (!isBrowser()) {
    return authToken;
  }
  if (!initializedToken) {
    authToken = (localStorage.getItem(TOKEN_KEY) || "").trim();
    initializedToken = true;
  }
  return authToken;
}

type ApiRequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string;
  body?: unknown;
  headers?: Record<string, string>;
};

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const currentToken = options.token ?? initializeAuthToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(currentToken ? { Authorization: `Bearer ${currentToken}` } : {}),
      ...(options.headers ?? {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = payload.detail;
      }
    } catch {
      // ignore parse failures
    }
    throw new Error(message);
  }

  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text) as T;
}
