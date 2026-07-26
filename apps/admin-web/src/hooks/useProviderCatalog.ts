import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '../utils/apiClient';
import type { ProviderCatalogItem } from '../types';

export function useListProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<{ data: ProviderCatalogItem[] }>('/providers'),
  });
}

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<ProviderCatalogItem, 'id' | 'status' | 'created_at' | 'updated_at'>) =>
      apiPost<ProviderCatalogItem>('/providers', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<ProviderCatalogItem> & { id: string }) =>
      apiPatch<ProviderCatalogItem>(`/providers/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete(`/providers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}

export function useValidateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ProviderCatalogItem>(`/providers/${id}/validate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });
}
