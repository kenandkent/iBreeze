import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { CompanyTask } from '../types';
import { logger } from '../utils/logger';

export function useListCompanyTasks(companyId: string, status?: string) {
  return useQuery({
    queryKey: ['companyTasks', companyId, status],
    queryFn: async (): Promise<CompanyTask[]> => {
      const start = performance.now();
      try {
        const result = await invoke<CompanyTask[]>('rpc_request', { method: 'task.list', params: { company_id: companyId, status } });
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
  return useQuery({
    queryKey: ['companyTask', companyId, taskId],
    queryFn: async (): Promise<CompanyTask> => {
      const start = performance.now();
      try {
        const result = await invoke<CompanyTask>('rpc_request', { method: 'task.get', params: { company_id: companyId, task_id: taskId } });
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
  return useMutation({
    mutationFn: async (params: { company_id: string; task_id: string; employee_id: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'task.confirmPlan', params });
        logger.logHookSuccess('useTask', 'task.confirmPlan', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useTask', 'task.confirmPlan', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['companyTasks'] }); },
  });
}

export function useCancelTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; task_id: string; employee_id: string; reason?: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'task.cancel', params });
        logger.logHookSuccess('useTask', 'task.cancel', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useTask', 'task.cancel', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['companyTasks'] }); },
  });
}
