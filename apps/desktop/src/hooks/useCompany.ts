import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Company } from '../types';
import { logger } from '../utils/logger';

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
      const start = performance.now();
      try {
        const result = await invoke<Company[]>('rpc_request', { method: 'company.list', params: {} });
        logger.logHookSuccess('useCompany', 'company.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useGetCompany(id: string) {
  return useQuery({
    queryKey: ['companies', id],
    queryFn: async (): Promise<Company> => {
      const start = performance.now();
      try {
        const result = await invoke<Company>('rpc_request', { method: 'company.get', params: { id } });
        logger.logHookSuccess('useCompany', 'company.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!id,
  });
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; email?: string; phone?: string; industry?: string; address?: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Company>('rpc_request', { method: 'company.create', params: { data } });
        logger.logHookSuccess('useCompany', 'company.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.create', e as Error, performance.now() - start);
        throw e;
      }
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
      const start = performance.now();
      try {
        const { id, ...rest } = data;
        const result = await invoke<Company>('rpc_request', { method: 'company.update', params: { id, data: rest } });
        logger.logHookSuccess('useCompany', 'company.update', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.update', e as Error, performance.now() - start);
        throw e;
      }
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
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'company.archive', params: { id } });
        logger.logHookSuccess('useCompany', 'company.archive', performance.now() - start);
      } catch (e) {
        logger.logHookError('useCompany', 'company.archive', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}
