import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ModelCatalogItem } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: () => fetchJson<{ data: ModelCatalogItem[] }>(`${API_BASE}/models`),
  });
}

export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<ModelCatalogItem, 'id' | 'status' | 'created_at' | 'updated_at'>) =>
      fetchJson<ModelCatalogItem>(`${API_BASE}/models`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function useUpdateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<ModelCatalogItem> & { id: string }) =>
      fetchJson<ModelCatalogItem>(`${API_BASE}/models/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/models/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function useValidateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<ModelCatalogItem>(`${API_BASE}/models/${id}/validate`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function usePublishModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<ModelCatalogItem>(`${API_BASE}/models/${id}/revisions`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}
