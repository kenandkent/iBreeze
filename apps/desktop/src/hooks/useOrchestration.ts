import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Orchestration, OrchestrationRun } from '../types';
import { logger } from '../utils/logger';

export function useListOrchestrations() {
  return useQuery({
    queryKey: ['orchestrations'],
    queryFn: async (): Promise<Orchestration[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Orchestration[]>('rpc_request', { method: 'task.list', params: {} });
        logger.logHookSuccess('useOrchestration', 'task.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useGetOrchestration(id: string) {
  return useQuery({
    queryKey: ['orchestrations', id],
    queryFn: async (): Promise<Orchestration> => {
      const start = performance.now();
      try {
        const list = await invoke<Orchestration[]>('rpc_request', { method: 'task.list', params: {} });
        const item = list.find((o) => o.id === id);
        if (!item) throw new Error('编排不存在');
        logger.logHookSuccess('useOrchestration', 'task.get', performance.now() - start);
        return item;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!id,
  });
}

export function useCreateOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Orchestration>('rpc_request', { method: 'task.confirmPlan', params: { name: data.name } });
        logger.logHookSuccess('useOrchestration', 'task.confirmPlan', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.confirmPlan', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
    },
  });
}

export function useUpdateOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; name?: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Orchestration>('rpc_request', { method: 'task.resume', params: { name: data.name || '' } });
        logger.logHookSuccess('useOrchestration', 'task.update', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.update', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
    },
  });
}

export function useDeleteOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'task.cancel', params: { id: _id } });
        logger.logHookSuccess('useOrchestration', 'task.cancel', performance.now() - start);
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.cancel', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
    },
  });
}

export function useRunOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orchestrationId: string) => {
      const start = performance.now();
      try {
        const result = await invoke<OrchestrationRun>('rpc_request', { method: 'task.resume', params: { id: orchestrationId } });
        logger.logHookSuccess('useOrchestration', 'task.run', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.run', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_, orchestrationId) => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
      queryClient.invalidateQueries({ queryKey: ['orchestrations', orchestrationId, 'runs'] });
    },
  });
}

export function useListOrchestrationRuns(_orchestrationId: string) {
  return useQuery({
    queryKey: ['orchestration-runs'],
    queryFn: async (): Promise<OrchestrationRun[]> => {
      const start = performance.now();
      try {
        const result = await invoke<OrchestrationRun[]>('rpc_request', { method: 'task.list', params: {} });
        logger.logHookSuccess('useOrchestration', 'task.listRuns', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useOrchestration', 'task.listRuns', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}
