import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { CompanyTask } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListCompanyTasks(companyId: string, status?: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.taskList(ctx, companyId, status),
    queryFn: async (): Promise<CompanyTask[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<CompanyTask[]>('task.list', { company_id: companyId, status });
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

export function useGetCompanyTask(companyId: string, taskId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.task(ctx, companyId, taskId),
    queryFn: async (): Promise<CompanyTask> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<CompanyTask>('task.get', { company_id: companyId, task_id: taskId });
        logger.logHookSuccess('useTask', 'task.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useTask', 'task.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!taskId,
  });
}

export function useConfirmPlan() {
  const qc = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; company_task_id: string; plan_artifact_id: string; plan_sha256: string; expected_version: number }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('task.confirmPlan', {
          company_id: params.company_id,
          company_task_id: params.company_task_id,
          plan_artifact_id: params.plan_artifact_id,
          plan_sha256: params.plan_sha256,
          expected_version: params.expected_version,
        });
        logger.logHookSuccess('useTask', 'task.confirmPlan', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useTask', 'task.confirmPlan', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.all(ctx) }); },
  });
}

export function useCancelTask() {
  const qc = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; task_id: string; employee_id: string; reason?: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('task.cancel', {
          company_id: params.company_id,
          task_id: params.task_id,
          employee_id: params.employee_id,
          reason: params.reason,
        });
        logger.logHookSuccess('useTask', 'task.cancel', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useTask', 'task.cancel', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.all(ctx) }); },
  });
}
