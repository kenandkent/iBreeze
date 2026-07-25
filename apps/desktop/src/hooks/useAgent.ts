import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { AgentInfo } from '../types';
import { logger } from '../utils/logger';

export function useListAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: async (): Promise<AgentInfo[]> => {
      const start = performance.now();
      try {
        const result = await invoke<AgentInfo[]>('rpc_request', { method: 'employee.list', params: {} });
        logger.logHookSuccess('useAgent', 'employee.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useAgent', 'employee.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    refetchInterval: 5000,
  });
}

export function useRunAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { agent_id: string; message: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'runtime.run', params: { agentId: data.agent_id, message: data.message } });
        logger.logHookSuccess('useAgent', 'runtime.run', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useAgent', 'runtime.run', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

export function useStopAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'runtime.stop', params: { agentId } });
        logger.logHookSuccess('useAgent', 'runtime.stop', performance.now() - start);
      } catch (e) {
        logger.logHookError('useAgent', 'runtime.stop', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}
