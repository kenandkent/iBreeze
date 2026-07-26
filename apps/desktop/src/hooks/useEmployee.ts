import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Employee } from '../types';
import { logger } from '../utils/logger';

export function useListEmployees(companyId: string, departmentId?: string) {
  return useQuery({
    queryKey: ['employees', companyId, departmentId],
    queryFn: async (): Promise<{ items: Employee[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const filter: Record<string, unknown> = departmentId ? { department_id: departmentId } : {};
        const result = await invoke<{ items: Employee[]; next_cursor: string | null; has_more: boolean }>(
          'rpc_request',
          { method: 'employee.list', params: { company_id: companyId, filter, cursor: null, limit: 50 } },
        );
        logger.logHookSuccess('useEmployee', 'employee.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useEmployee', 'employee.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useCreateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: {
      company_id: string;
      department_id: string;
      display_name: string;
      base_profile_version_id: string;
      workflow_role: string;
    }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'employee.create', params });
        logger.logHookSuccess('useEmployee', 'employee.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useEmployee', 'employee.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_: unknown, vars: { company_id: string; department_id: string; display_name: string; base_profile_version_id: string; workflow_role: string }) => {
      qc.invalidateQueries({ queryKey: ['employees', vars.company_id] });
    },
  });
}
