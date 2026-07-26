import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Workspace } from '../types';
import { logger } from '../utils/logger';

export function useListWorkspaces(companyId: string) {
  return useQuery({
    queryKey: ['workspaces', companyId],
    queryFn: async (): Promise<Workspace[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Workspace[]>('rpc_request', { method: 'workspace.list', params: { company_id: companyId } });
        logger.logHookSuccess('useWorkspace', 'workspace.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useGetWorkspace(companyId: string, workspaceId: string) {
  return useQuery({
    queryKey: ['workspaces', workspaceId],
    queryFn: async (): Promise<Workspace> => {
      const start = performance.now();
      try {
        const result = await invoke<Workspace>('rpc_request', { method: 'workspace.get', params: { company_id: companyId, workspace_id: workspaceId } });
        logger.logHookSuccess('useWorkspace', 'workspace.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!workspaceId,
  });
}

export function useApplyWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; workspace_id: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'workspace.apply', params: { company_id: params.company_id, workspace_id: params.workspace_id } });
        logger.logHookSuccess('useWorkspace', 'workspace.apply', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.apply', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

export function useAbandonWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; workspace_id: string }) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'workspace.abandon', params: { company_id: params.company_id, workspace_id: params.workspace_id } });
        logger.logHookSuccess('useWorkspace', 'workspace.abandon', performance.now() - start);
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.abandon', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}
