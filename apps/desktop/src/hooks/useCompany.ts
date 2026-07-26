import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Company } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

interface CompanyListParams {
  filter?: Record<string, unknown>;
  cursor?: string;
  limit?: number;
}

export function useListCompanies(params: CompanyListParams = {}) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.companyList(ctx),
    queryFn: async (): Promise<{ items: Company[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<{ items: Company[]; next_cursor: string | null; has_more: boolean }>(
          'company.list',
          { filter: params.filter ?? {}, cursor: params.cursor ?? null, limit: params.limit ?? 50 },
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
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.company(ctx, companyId),
    queryFn: async (): Promise<Company> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Company>('company.get', { id: companyId, company_id: companyId });
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
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (data: { name: string; introduction: string; general_manager_name: string; base_profile_version_id: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Company>('company.create', {
          name: data.name,
          introduction: data.introduction,
          general_manager_name: data.general_manager_name,
          base_profile_version_id: data.base_profile_version_id,
        });
        logger.logHookSuccess('useCompany', 'company.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}

export function useUpdateCompany() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (data: { company_id: string; name?: string; introduction?: string; expected_version: number }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Company>('company.update', {
          company_id: data.company_id,
          name: data.name,
          introduction: data.introduction,
          expected_version: data.expected_version,
        });
        logger.logHookSuccess('useCompany', 'company.update', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useCompany', 'company.update', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
      queryClient.invalidateQueries({ queryKey: queryKeys.company(ctx, variables.company_id) });
    },
  });
}

export function useDeleteCompany() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; expected_version: number }) => {
      const start = performance.now();
      try {
        await createRpcRequest('company.archive', {
          company_id: params.company_id,
          expected_version: params.expected_version,
        });
        logger.logHookSuccess('useCompany', 'company.archive', performance.now() - start);
      } catch (e) {
        logger.logHookError('useCompany', 'company.archive', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}
