import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../utils/apiClient';
import type { Release } from '../types';

export function useListReleases() {
  return useQuery({
    queryKey: ['releases'],
    queryFn: () => apiGet<{ data: Release[] }>('/catalog/releases'),
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

export function useEmergencyDisable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { resource_type: string; resource_id: string; version?: string; reason: string; emergency_code: string }) =>
      apiPost<void>('/emergency-disables', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  });
}
