import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Release } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListReleases() {
  return useQuery({
    queryKey: ['releases'],
    queryFn: () => fetchJson<{ data: Release[] }>(`${API_BASE}/catalog/releases`),
  });
}

export function useGetManifest(id: string) {
  return useQuery({
    queryKey: ['release-manifest', id],
    queryFn: () => fetchJson<{ data: Record<string, unknown> }>(`${API_BASE}/catalog/releases/${id}`),
    enabled: !!id,
  });
}

export function useCreateRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { version: string; notes?: string }) =>
      fetchJson<Release>(`${API_BASE}/catalog/releases`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  });
}

export function useEmergencyDisable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { resource_type: string; resource_id: string; version?: string; reason: string; emergency_code: string }) =>
      fetchJson<void>(`${API_BASE}/emergency-disables`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  });
}
