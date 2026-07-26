import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Department } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListDepartments(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.departmentList(ctx, companyId),
    queryFn: async (): Promise<{ items: Department[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<{ items: Department[]; next_cursor: string | null; has_more: boolean }>(
          'department.list',
          { company_id: companyId, filter: {}, cursor: null, limit: 50 },
        );
        logger.logHookSuccess('useDepartment', 'department.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useDepartment', 'department.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useCreateDepartment() {
  const qc = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: {
      company_id: string;
      name: string;
      function_description: string;
      leader_name: string;
      base_profile_version_id: string;
    }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('department.create', params);
        logger.logHookSuccess('useDepartment', 'department.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useDepartment', 'department.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.departmentList(ctx, (vars as { company_id: string }).company_id) });
    },
  });
}
