import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Company } from '../types';

interface CompanyListParams {
  search?: string;
  status?: string;
  cursor?: string;
  limit?: number;
}

export function useListCompanies(_params: CompanyListParams = {}) {
  return useQuery({
    queryKey: ['companies'],
    queryFn: async (): Promise<Company[]> => {
      return invoke<Company[]>('list_companies');
    },
  });
}

export function useGetCompany(id: string) {
  return useQuery({
    queryKey: ['companies', id],
    queryFn: async (): Promise<Company> => {
      return invoke<Company>('get_company', { id });
    },
    enabled: !!id,
  });
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; email?: string; phone?: string; industry?: string; address?: string }) => {
      return invoke<Company>('create_company', { data });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}

export function useUpdateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; name?: string; email?: string; phone?: string; industry?: string; address?: string }) => {
      const { id, ...rest } = data;
      return invoke<Company>('update_company', { id, data: rest });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      queryClient.invalidateQueries({ queryKey: ['companies', variables.id] });
    },
  });
}

export function useDeleteCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await invoke('delete_company', { id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}
