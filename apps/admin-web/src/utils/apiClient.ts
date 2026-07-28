import { useAuthStore } from '../stores/authStore';

interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  reference_id?: string;
  [key: string]: unknown;
}

const API_BASE = '/admin/api/v1';

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: string;
  reference_id?: string;

  constructor(status: number, problem?: ProblemDetails) {
    super(problem?.detail || problem?.title || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = problem?.code;
    this.detail = problem?.detail;
    this.reference_id = problem?.reference_id;
  }
}

function generateIdempotencyKey(): string {
  return crypto.randomUUID();
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
}

export async function apiPatch<T>(path: string, body: unknown, version?: number): Promise<T> {
  return apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) }, version);
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'PUT', body: JSON.stringify(body) });
}

export async function apiDelete<T = void>(path: string, version?: number): Promise<T> {
  return apiFetch<T>(path, { method: 'DELETE' }, version);
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body: formData, headers: {} });
}

let refreshing: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (refreshing) return refreshing;
  const token = useAuthStore.getState().token;
  if (!token) return false;
  refreshing = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) return false;
      const data = await res.json();
      useAuthStore.getState().login(data.data.access_token, data.data.user);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

async function apiFetch<T>(path: string, options?: RequestInit, version?: number): Promise<T> {
  const token = useAuthStore.getState().token;
  const isWrite = options?.method ? WRITE_METHODS.has(options.method) : false;

  const headers: Record<string, string> = {};
  if (isWrite && options?.method !== 'DELETE') {
    headers['Content-Type'] = 'application/json';
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (isWrite) {
    headers['Idempotency-Key'] = generateIdempotencyKey();
  }
  if (version !== undefined) {
    headers['If-Match'] = `"${version}"`;
  }

  const mergedOptions: RequestInit = {
    ...options,
    credentials: 'include',
    headers: { ...headers, ...(options?.headers as Record<string, string>) },
  };

  let attempt = 0;
  while (attempt < 2) {
    const res = await fetch(`${API_BASE}${path}`, mergedOptions);

    if (res.status === 401 && attempt === 0) {
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        if (token) {
          mergedOptions.headers = {
            ...mergedOptions.headers,
            'Authorization': `Bearer ${useAuthStore.getState().token}`,
          };
        }
        attempt++;
        continue;
      }
      useAuthStore.getState().logout();
      window.location.href = '/login';
      throw new ApiError(401, { code: 'UNAUTHORIZED', detail: 'Session expired' });
    }

    if (!res.ok) {
      let problem: ProblemDetails | undefined;
      try {
        problem = await res.json();
      } catch { /* ignore parse error, problem stays undefined */ }
      throw new ApiError(res.status, problem);
    }

    if (res.status === 204) return undefined as T;
    return res.json();
  }

  throw new ApiError(401, { code: 'UNAUTHORIZED', detail: 'Session expired after refresh' });
}
