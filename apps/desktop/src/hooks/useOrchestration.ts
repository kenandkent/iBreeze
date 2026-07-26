import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Orchestration, OrchestrationRun } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListOrchestrations() {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.orchestrationList(ctx),
    queryFn: async (): Promise<Orchestration[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Orchestration[]>('orchestration.list', {});
        logger.logHookSuccess('useOrchestration', 'orchestration.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'orchestration.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useListOrchestrationRuns(orchestrationId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.orchestrationRunList(ctx, orchestrationId),
    queryFn: async (): Promise<OrchestrationRun[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<OrchestrationRun[]>('orchestration.listRuns', { orchestration_id: orchestrationId });
        logger.logHookSuccess('useOrchestration', 'orchestration.listRuns', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'orchestration.listRuns', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!orchestrationId,
  });
}

export function useCreateOrchestration() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (data: { name: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Orchestration>('orchestration.create', { name: data.name });
        logger.logHookSuccess('useOrchestration', 'orchestration.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'orchestration.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.orchestrationList(ctx) });
    },
  });
}

export function useRunOrchestration() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (orchestrationId: string) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<OrchestrationRun>('orchestration.run', { orchestration_id: orchestrationId });
        logger.logHookSuccess('useOrchestration', 'orchestration.run', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'orchestration.run', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}

export function useDeleteOrchestration() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (id: string) => {
      const start = performance.now();
      try {
        await createRpcRequest('orchestration.archive', { orchestration_id: id });
        logger.logHookSuccess('useOrchestration', 'orchestration.archive', performance.now() - start);
      } catch (e) {
        logger.logHookError('useOrchestration', 'orchestration.archive', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.orchestrationList(ctx) });
    },
  });
}
