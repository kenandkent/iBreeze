import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Workspace } from '../types';
import { logger } from '../utils/logger';

export function useListWorkspaces() {
  return useQuery({
    queryKey: ['workspaces'],
    queryFn: async (): Promise<Workspace[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Workspace[]>('rpc_request', { method: 'workspace.list', params: {} });
        logger.logHookSuccess('useWorkspace', 'workspace.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useGetWorkspace(id: string) {
  return useQuery({
    queryKey: ['workspaces', id],
    queryFn: async (): Promise<Workspace> => {
      const start = performance.now();
      try {
        const result = await invoke<Workspace>('rpc_request', { method: 'workspace.get', params: { id } });
        logger.logHookSuccess('useWorkspace', 'workspace.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!id,
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Workspace>('rpc_request', { method: 'workspace.get', params: { name: data.name } });
        logger.logHookSuccess('useWorkspace', 'workspace.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

export function useUpdateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; name?: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Workspace>('rpc_request', { method: 'workspace.apply', params: { name: data.name || '' } });
        logger.logHookSuccess('useWorkspace', 'workspace.update', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.update', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'workspace.abandon', params: { id: _id } });
        logger.logHookSuccess('useWorkspace', 'workspace.delete', performance.now() - start);
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.delete', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

export function useAddWorkspaceMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_data: { workspace_id: string; user_id: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'workspace.get', params: { workspace_id: _data.workspace_id, user_id: _data.user_id } });
        logger.logHookSuccess('useWorkspace', 'workspace.addMember', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.addMember', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

export function useRemoveWorkspaceMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_data: { workspace_id: string; member_id: string }) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'workspace.abandon', params: { workspace_id: _data.workspace_id, member_id: _data.member_id } });
        logger.logHookSuccess('useWorkspace', 'workspace.removeMember', performance.now() - start);
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.removeMember', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}
