import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '../utils/apiClient';
import type { AdminUser } from '../types';

export function useListAdminUsers() {
  return useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiGet<{ data: AdminUser[] }>('/users'),
  });
}

export function useCreateAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string; user_type: 'admin' | 'app_user'; role?: string }) =>
      apiPost<AdminUser>('/users', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useUpdateAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; display_name?: string; status?: string }) =>
      apiPatch<AdminUser>(`/users/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useDeleteAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete(`/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useResetPassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_password }: { id: string; new_password: string }) =>
      apiPost<void>(`/users/${id}/reset-password`, { new_password }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useRevokeSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<void>(`/users/${id}/revoke-sessions`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}
