import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { AgentCatalogItem } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: () => fetchJson<{ data: AgentCatalogItem[] }>(`${API_BASE}/agents`),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { key: string; display_name: string; description?: string }) =>
      fetchJson<AgentCatalogItem>(`${API_BASE}/agents`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; display_name?: string; description?: string }) =>
      fetchJson<AgentCatalogItem>(`${API_BASE}/agents/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/agents/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useValidateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<AgentCatalogItem>(`${API_BASE}/agents/${id}/validate`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function usePublishAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<AgentCatalogItem>(`${API_BASE}/agents/${id}/revisions`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}
