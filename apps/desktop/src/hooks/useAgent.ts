import { useQuery } from '@tanstack/react-query';
import type { AgentInfo } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListAgents(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.employeeList(ctx, companyId),
    queryFn: async (): Promise<AgentInfo[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<AgentInfo[]>('employee.list', { company_id: companyId, filter: {}, cursor: null, limit: 50 });
        logger.logHookSuccess('useAgent', 'employee.list', performance.now() - start);
        return result as unknown as AgentInfo[];
      } catch (e) {
        logger.logHookError('useAgent', 'employee.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
    refetchInterval: 5000,
  });
}
