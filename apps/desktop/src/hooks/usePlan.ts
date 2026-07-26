import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { PlanVersion } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListPlanVersions(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.planVersionList(ctx, companyId),
    queryFn: async (): Promise<PlanVersion[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<PlanVersion[]>('planVersion.list', { company_id: companyId });
        logger.logHookSuccess('usePlan', 'planVersion.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('usePlan', 'planVersion.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
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
