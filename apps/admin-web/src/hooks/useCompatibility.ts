import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '../utils/apiClient';
import type { CompatibilityRule } from '../types';

export function useListCompatibilityRules() {
  return useQuery({
    queryKey: ['compatibility-rules'],
    queryFn: () => apiGet<{ data: CompatibilityRule[] }>('/compatibility-rules'),
  });
}

export function useCreateCompatibilityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<CompatibilityRule, 'id' | 'created_at' | 'updated_at'>) =>
      apiPost<CompatibilityRule>('/compatibility-rules', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compatibility-rules'] }),
  });
}

export function useUpdateCompatibilityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<CompatibilityRule> & { id: string }) =>
      apiPatch<CompatibilityRule>(`/compatibility-rules/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compatibility-rules'] }),
  });
}

export function useDeleteCompatibilityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete(`/compatibility-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compatibility-rules'] }),
  });
}

export function useEvaluateCompatibilityRule() {
  return useMutation({
    mutationFn: (data: { agent_key: string; model_key: string; provider_key?: string }) =>
      apiPost<{ result: string }>('/compatibility-rules/evaluate', data),
  });
}
