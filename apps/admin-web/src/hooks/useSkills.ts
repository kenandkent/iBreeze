import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiDelete, apiUpload } from '../utils/apiClient';
import type { SkillCatalogItem } from '../types';

export function useListSkills() {
  return useQuery({
    queryKey: ['skills'],
    queryFn: () => apiGet<{ data: SkillCatalogItem[] }>('/skills'),
  });
}

export function useInstallSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { skill_key: string; version: string; agent_bindings?: string[] }) =>
      apiPost<SkillCatalogItem>('/skills', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}

export function useRemoveSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiDelete(`/skills/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}

export function useUploadSkillVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ skillId, formData }: { skillId: string; formData: FormData }) =>
      apiUpload(`/skills/${skillId}/versions`, formData),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}
