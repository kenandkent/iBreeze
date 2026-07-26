import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { AgentInfo } from '../types';
import { logger } from '../utils/logger';

export function useListAgents(companyId: string) {
  return useQuery({
    queryKey: ['agents', companyId],
    queryFn: async (): Promise<AgentInfo[]> => {
      const start = performance.now();
      try {
        const result = await invoke<AgentInfo[]>('rpc_request', { method: 'employee.list', params: { company_id: companyId, filter: {}, cursor: null, limit: 50 } });
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

export function useRunAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { company_id: string; agent_id: string; message: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'runtime.run', params: { company_id: data.company_id, agent_id: data.agent_id, message: data.message } });
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
    mutationFn: async (params: { company_id: string; agent_id: string }) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'runtime.stop', params: { company_id: params.company_id, agent_id: params.agent_id } });
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
