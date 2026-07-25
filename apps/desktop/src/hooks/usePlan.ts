import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { PlanVersion } from '../types';
import { logger } from '../utils/logger';

export function useListPlanVersions(companyId: string) {
  return useQuery({
    queryKey: ['planVersions', companyId],
    queryFn: async (): Promise<PlanVersion[]> => {
      const start = performance.now();
      try {
        const result = await invoke<PlanVersion[]>('rpc_request', { method: 'task.list', params: { company_id: companyId } });
        logger.logHookSuccess('usePlan', 'task.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('usePlan', 'task.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useConfirmPlanVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; approval_id: string; employee_id: string; decision: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'approval.resolve', params });
        logger.logHookSuccess('usePlan', 'approval.resolve', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('usePlan', 'approval.resolve', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['planVersions'] }); },
  });
}
