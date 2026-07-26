import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Workspace } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useGetWorkspace(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.workspaceList(ctx, companyId),
    queryFn: async (): Promise<Workspace> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Workspace>('workspace.get', { company_id: companyId });
        logger.logHookSuccess('useWorkspace', 'workspace.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useGetWorkspaceById(companyId: string, workspaceId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.workspace(ctx, companyId, workspaceId),
    queryFn: async (): Promise<Workspace> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Workspace>('workspace.get', { company_id: companyId, workspace_id: workspaceId });
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
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; workspace_id: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('workspace.apply', {
          company_id: params.company_id,
          workspace_id: params.workspace_id,
        });
        logger.logHookSuccess('useWorkspace', 'workspace.apply', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.apply', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workspaceList(ctx, variables.company_id) });
    },
  });
}

export function useAbandonWorkspace() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; workspace_id: string }) => {
      const start = performance.now();
      try {
        await createRpcRequest('workspace.abandon', {
          company_id: params.company_id,
          workspace_id: params.workspace_id,
        });
        logger.logHookSuccess('useWorkspace', 'workspace.abandon', performance.now() - start);
      } catch (e) {
        logger.logHookError('useWorkspace', 'workspace.abandon', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workspaceList(ctx, variables.company_id) });
    },
  });
}
