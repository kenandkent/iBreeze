import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Employee } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListEmployees(companyId: string, departmentId?: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.employee(ctx, companyId, departmentId),
    queryFn: async (): Promise<{ items: Employee[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const filter: Record<string, unknown> = departmentId ? { department_id: departmentId } : {};
        const result = await createRpcRequest<{ items: Employee[]; next_cursor: string | null; has_more: boolean }>(
          'employee.list',
          { company_id: companyId, filter, cursor: null, limit: 50 },
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
  const ctx = useQueryCtx();
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
        const result = await createRpcRequest('employee.create', params);
        logger.logHookSuccess('useEmployee', 'employee.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useEmployee', 'employee.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.employeeList(ctx, (vars as { company_id: string }).company_id) });
    },
  });
}
