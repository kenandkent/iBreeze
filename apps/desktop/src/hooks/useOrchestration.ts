import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Orchestration, OrchestrationRun } from '../types';

// 列出编排
export function useListOrchestrations() {
  return useQuery({
    queryKey: ['orchestrations'],
    queryFn: async (): Promise<Orchestration[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.list
      return [];
    },
  });
}

// 获取单个编排详情
export function useGetOrchestration(id: string) {
  return useQuery({
    queryKey: ['orchestrations', id],
    queryFn: async (): Promise<Orchestration> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.get
      throw new Error('Not implemented');
    },
    enabled: !!id,
  });
}

// 创建编排
export function useCreateOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; description?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.create
      return {
        id: crypto.randomUUID(),
        ...data,
        version: 1,
        status: 'draft',
        nodes: [],
        edges: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Orchestration;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
    },
  });
}

// 更新编排
export function useUpdateOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; name?: string; description?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.update
      return { ...data, updated_at: new Date().toISOString() };
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
      queryClient.invalidateQueries({ queryKey: ['orchestrations', variables.id] });
    },
  });
}

// 删除编排
export function useDeleteOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.delete
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
    },
  });
}

// 运行编排
export function useRunOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orchestrationId: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.run
      return {
        id: crypto.randomUUID(),
        orchestration_id: orchestrationId,
        status: 'running' as const,
        started_at: new Date().toISOString(),
      } as OrchestrationRun;
    },
    onSuccess: (_, orchestrationId) => {
      queryClient.invalidateQueries({ queryKey: ['orchestrations'] });
      queryClient.invalidateQueries({ queryKey: ['orchestrations', orchestrationId, 'runs'] });
    },
  });
}

// 获取运行历史
export function useListOrchestrationRuns(orchestrationId: string) {
  return useQuery({
    queryKey: ['orchestrations', orchestrationId, 'runs'],
    queryFn: async (): Promise<OrchestrationRun[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC orchestration.runs
      return [];
    },
    enabled: !!orchestrationId,
  });
}
