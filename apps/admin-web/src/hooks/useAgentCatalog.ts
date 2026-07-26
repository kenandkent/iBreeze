import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '../utils/apiClient';
import type { AgentCatalogItem } from '../types';

export function useListAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: () => apiGet<{ data: AgentCatalogItem[] }>('/agents'),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { key: string; display_name: string; description?: string }) =>
      apiPost<AgentCatalogItem>('/agents', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; display_name?: string; description?: string }) =>
      apiPatch<AgentCatalogItem>(`/agents/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete(`/agents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useValidateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<AgentCatalogItem>(`/agents/${id}/validate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function usePublishAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<AgentCatalogItem>(`/agents/${id}/publish`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}
