import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { AdminUser } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListAdminUsers() {
  return useQuery({
    queryKey: ['admin-users'],
    queryFn: () => fetchJson<{ data: AdminUser[] }>(`${API_BASE}/users`),
  });
}

export function useCreateAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string; user_type: 'admin' | 'app_user'; role?: string }) =>
      fetchJson<AdminUser>(`${API_BASE}/users`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useUpdateAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; display_name?: string; status?: string }) =>
      fetchJson<AdminUser>(`${API_BASE}/users/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useDeleteAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/users/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useResetPassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_password }: { id: string; new_password: string }) =>
      fetchJson<void>(`${API_BASE}/users/${id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ new_password }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useRevokeSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/users/${id}/revoke-sessions`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}
