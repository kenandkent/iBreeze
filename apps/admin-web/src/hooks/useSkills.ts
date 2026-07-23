import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { SkillCatalogItem } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useListSkills() {
  return useQuery({
    queryKey: ['skills'],
    queryFn: () => fetchJson<{ data: SkillCatalogItem[] }>(`${API_BASE}/skills`),
  });
}

export function useInstallSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { skill_key: string; version: string; agent_bindings?: string[] }) =>
      fetchJson<SkillCatalogItem>(`${API_BASE}/skills`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}

export function useRemoveSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/skills/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}

export function useEmergencyDisableSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`${API_BASE}/skills/${id}/validate`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}
