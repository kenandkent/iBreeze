import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Company } from '../types';
import { logger } from '../utils/logger';

interface CompanyListParams {
  filter?: Record<string, unknown>;
  cursor?: string;
  limit?: number;
}

export function useListCompanies(params: CompanyListParams = {}) {
  return useQuery({
    queryKey: ['companies'],
    queryFn: async (): Promise<{ items: Company[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const result = await invoke<{ items: Company[]; next_cursor: string | null; has_more: boolean }>(
          'rpc_request',
          { method: 'company.list', params: { filter: params.filter ?? {}, cursor: params.cursor ?? null, limit: params.limit ?? 50 } },
        );
        logger.logHookSuccess('useCompany', 'company.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useGetCompany(companyId: string) {
  return useQuery({
    queryKey: ['companies', companyId],
    queryFn: async (): Promise<Company> => {
      const start = performance.now();
      try {
        const result = await invoke<Company>('rpc_request', { method: 'company.get', params: { id: companyId, company_id: companyId } });
        logger.logHookSuccess('useCompany', 'company.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; introduction: string; general_manager_name: string; base_profile_version_id: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Company>('rpc_request', {
          method: 'company.create',
          params: { name: data.name, introduction: data.introduction, general_manager_name: data.general_manager_name, base_profile_version_id: data.base_profile_version_id },
        });
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
    mutationFn: async (data: { company_id: string; name?: string; introduction?: string; expected_version: number }) => {
      const start = performance.now();
      try {
        const result = await invoke<Company>('rpc_request', {
          method: 'company.update',
          params: { company_id: data.company_id, name: data.name, introduction: data.introduction, expected_version: data.expected_version },
        });
        logger.logHookSuccess('useCompany', 'company.update', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.update', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      queryClient.invalidateQueries({ queryKey: ['companies', variables.company_id] });
    },
  });
}

export function useDeleteCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; expected_version: number }) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'company.archive', params: { company_id: params.company_id, expected_version: params.expected_version } });
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
