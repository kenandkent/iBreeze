import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../utils/apiClient';
import type { Release } from '../types';

export function useListReleases() {
  return useQuery({
    queryKey: ['releases'],
    queryFn: () => apiGet<{ items: Release[] }>('/catalog/releases'),
  });
}

export function useCreateRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { version: string; notes?: string }) =>
      apiPost<Release>('/catalog/releases', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  });
}

export function useReconcileRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<Release>(`/catalog/releases/${id}/reconcile`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  });
}

export function usePublishRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<Release>(`/catalog/releases/${id}/publish`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  });
}

export function useEmergencyDisable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      resource_type: string;
      resource_id: string;
      resource_version?: string;
      action: string;
      reason: string;
      code: string;
    }) =>
      apiPost<void>('/emergency-disables', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['latest-emergency-disable'] });
      qc.invalidateQueries({ queryKey: ['releases'] });
    },
  });
}

export function useLatestEmergencyDisable() {
  return useQuery({
    queryKey: ['latest-emergency-disable'],
    queryFn: () => apiGet<{
      id: string;
      sequence: number;
      resource_type?: string;
      resource_id?: string;
      created_at: string;
    }>('/emergency-disables/latest'),
  });
}
