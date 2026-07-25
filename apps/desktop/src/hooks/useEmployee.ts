import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Employee } from '../types';
import { logger } from '../utils/logger';

export function useListEmployees(companyId: string) {
  return useQuery({
    queryKey: ['employees', companyId],
    queryFn: async (): Promise<Employee[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Employee[]>('rpc_request', { method: 'employee.list', params: { company_id: companyId } });
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
    mutationFn: async (params: { company_id: string; department_id: string; display_name: string; role: string }) => {
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
    onSuccess: (_: unknown, vars: { company_id: string; department_id: string; display_name: string; role: string }) => { qc.invalidateQueries({ queryKey: ['employees', vars.company_id] }); },
  });
}
