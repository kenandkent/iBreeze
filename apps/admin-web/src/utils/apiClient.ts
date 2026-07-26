import { useAuthStore } from '../stores/authStore';

interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  [key: string]: unknown;
}

const API_BASE = '/admin/api/v1';

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: string;

  constructor(status: number, problem?: ProblemDetails) {
    super(problem?.detail || problem?.title || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = problem?.code;
    this.detail = problem?.detail;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
}

export async function apiDelete<T = void>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: 'DELETE' });
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options?.headers as Record<string, string>) },
  });

  if (!res.ok) {
    let problem: ProblemDetails | undefined;
    try {
      problem = await res.json();
    } catch {
      // ignore parse errors
    }

    if (res.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }

    throw new ApiError(res.status, problem);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}
