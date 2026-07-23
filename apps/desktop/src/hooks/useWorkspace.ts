import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Workspace, WorkspaceMember } from '../types';

// 列出工作区
export function useListWorkspaces() {
  return useQuery({
    queryKey: ['workspaces'],
    queryFn: async (): Promise<Workspace[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.list
      return [];
    },
  });
}

// 获取单个工作区详情
export function useGetWorkspace(id: string) {
  return useQuery({
    queryKey: ['workspaces', id],
    queryFn: async (): Promise<Workspace> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.get
      throw new Error('Not implemented');
    },
    enabled: !!id,
  });
}

// 创建工作区
export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; description?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.create
      return {
        id: crypto.randomUUID(),
        ...data,
        owner_id: '',
        status: 'active',
        members: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Workspace;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

// 更新工作区
export function useUpdateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; name?: string; description?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.update
      return { ...data, updated_at: new Date().toISOString() };
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
      queryClient.invalidateQueries({ queryKey: ['workspaces', variables.id] });
    },
  });
}

// 删除工作区
export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.delete
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}

// 添加成员
export function useAddWorkspaceMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { workspace_id: string; user_id: string; role?: WorkspaceMember['role'] }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.addMember
      return {
        id: crypto.randomUUID(),
        user_id: data.user_id,
        role: data.role || 'member',
        created_at: new Date().toISOString(),
      } as WorkspaceMember;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
      queryClient.invalidateQueries({ queryKey: ['workspaces', variables.workspace_id] });
    },
  });
}

// 移除成员
export function useRemoveWorkspaceMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_data: { workspace_id: string; member_id: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC workspace.removeMember
      return { success: true };
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
      queryClient.invalidateQueries({ queryKey: ['workspaces', variables.workspace_id] });
    },
  });
}
