import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Department } from '../types';
import { logger } from '../utils/logger';

export function useListDepartments(companyId: string) {
  return useQuery({
    queryKey: ['departments', companyId],
    queryFn: async (): Promise<{ items: Department[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const result = await invoke<{ items: Department[]; next_cursor: string | null; has_more: boolean }>(
          'rpc_request',
          { method: 'department.list', params: { company_id: companyId, filter: {}, cursor: null, limit: 50 } },
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
        const result = await invoke('rpc_request', { method: 'department.create', params });
        logger.logHookSuccess('useDepartment', 'department.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useDepartment', 'department.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_: unknown, vars: { company_id: string; name: string; function_description: string; leader_name: string; base_profile_version_id: string }) => {
      qc.invalidateQueries({ queryKey: ['departments', vars.company_id] });
    },
  });
}
