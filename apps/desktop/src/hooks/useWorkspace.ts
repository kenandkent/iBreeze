import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Workspace } from '../types';

export function useListWorkspaces() {
  return useQuery({
    queryKey: ['workspaces'],
    queryFn: async (): Promise<Workspace[]> => {
      return invoke<Workspace[]>('list_workspaces');
    },
  });
}

export function useGetWorkspace(id: string) {
  return useQuery({
    queryKey: ['workspaces', id],
    queryFn: async (): Promise<Workspace> => {
      return invoke<Workspace>('get_workspace', { id });
    },
    enabled: !!id,
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string }) => {
      return invoke<Workspace>('create_workspace', { name: data.name });
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
      return invoke<Workspace>('create_workspace', { name: data.name || '' });
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
      await invoke('delete_company', { id: _id });
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
      return invoke('create_workspace', { name: 'member' });
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
      await invoke('delete_company', { id: _data.member_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });
}
