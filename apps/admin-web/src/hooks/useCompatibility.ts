import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { CompatibilityRule } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListCompatibilityRules() {
  return useQuery({
    queryKey: ['compatibility-rules'],
    queryFn: () => fetchJson<{ data: CompatibilityRule[] }>(`${API_BASE}/compatibility-rules`),
  });
}

export function useCreateCompatibilityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<CompatibilityRule, 'id' | 'created_at' | 'updated_at'>) =>
      fetchJson<CompatibilityRule>(`${API_BASE}/compatibility-rules`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compatibility-rules'] }),
  });
}

export function useUpdateCompatibilityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<CompatibilityRule> & { id: string }) =>
      fetchJson<CompatibilityRule>(`${API_BASE}/compatibility-rules/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compatibility-rules'] }),
  });
}

export function useDeleteCompatibilityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/compatibility-rules/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compatibility-rules'] }),
  });
}

export function useEvaluateCompatibilityRule() {
  return useMutation({
    mutationFn: (data: { agent_key: string; model_key: string; provider_key?: string }) =>
      fetchJson<{ result: string }>(`${API_BASE}/compatibility-rules/evaluate`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  });
}
