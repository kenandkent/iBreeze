import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Task } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useGetTask(companyId: string, taskId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.task(ctx, companyId, taskId),
    queryFn: async (): Promise<Task> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Task>('task.get', { company_id: companyId, id: taskId });
        logger.logHookSuccess('usePlan', 'task.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('usePlan', 'task.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!taskId,
  });
}

export function useConfirmPlanVersion() {
  const qc = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; approval_id: string; employee_id: string; decision: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('approval.resolve', params);
        logger.logHookSuccess('usePlan', 'approval.resolve', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('usePlan', 'approval.resolve', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.all(ctx) }); },
  });
}
