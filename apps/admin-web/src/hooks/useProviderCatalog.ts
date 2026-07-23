import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ProviderCatalogItem } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => fetchJson<{ data: ProviderCatalogItem[] }>(`${API_BASE}/providers`),
  });
}

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<ProviderCatalogItem, 'id' | 'status' | 'created_at' | 'updated_at'>) =>
      fetchJson<ProviderCatalogItem>(`${API_BASE}/providers`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<ProviderCatalogItem> & { id: string }) =>
      fetchJson<ProviderCatalogItem>(`${API_BASE}/providers/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/providers/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}
