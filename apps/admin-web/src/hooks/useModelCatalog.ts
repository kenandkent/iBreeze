import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '../utils/apiClient';
import type { ModelCatalogItem } from '../types';

export function useListModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: () => apiGet<{ items: ModelCatalogItem[] }>('/models'),
  });
}

export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<ModelCatalogItem, 'id' | 'status' | 'created_at' | 'updated_at'>) =>
      apiPost<ModelCatalogItem>('/models', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function useUpdateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<ModelCatalogItem> & { id: string }) =>
      apiPatch<ModelCatalogItem>(`/models/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete(`/models/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export function useValidateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ModelCatalogItem>(`/models/${id}/validate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}
