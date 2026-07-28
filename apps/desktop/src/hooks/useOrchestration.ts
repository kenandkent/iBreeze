import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Task, Run } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListTasks(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.taskList(ctx, companyId),
    queryFn: async (): Promise<Task[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Task[]>('task.list', { company_id: companyId });
        logger.logHookSuccess('useTask', 'task.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useTask', 'task.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useGetTaskGraph(companyId: string, taskId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.all(ctx),
    queryFn: async (): Promise<Task> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Task>('task.getGraph', { company_id: companyId, id: taskId });
        logger.logHookSuccess('useOrchestration', 'task.getGraph', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.getGraph', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!taskId,
  });
}

export function useListRuns(companyId: string, taskId?: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.all(ctx),
    queryFn: async (): Promise<Run[]> => {
      const start = performance.now();
      try {
        const filter = taskId ? { task_id: taskId } : {};
        const result = await createRpcRequest<Run[]>('run.list', { company_id: companyId, filter, cursor: null, limit: 50 });
        logger.logHookSuccess('useOrchestration', 'run.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'run.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useRunTask() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (taskId: string) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('runtime.run', { id: taskId });
        logger.logHookSuccess('useOrchestration', 'runtime.run', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'runtime.run', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}
