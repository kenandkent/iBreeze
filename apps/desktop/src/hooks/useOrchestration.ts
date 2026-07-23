import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Orchestration, OrchestrationRun } from '../types';

export function useListOrchestrations() {
  return useQuery({
    queryKey: ['orchestrations'],
    queryFn: async (): Promise<Orchestration[]> => {
      return invoke<Orchestration[]>('list_orchestrations');
    },
  });
}

export function useGetOrchestration(id: string) {
  return useQuery({
    queryKey: ['orchestrations', id],
    queryFn: async (): Promise<Orchestration> => {
      const list = await invoke<Orchestration[]>('list_orchestrations');
      const item = list.find((o) => o.id === id);
      if (!item) throw new Error('编排不存在');
      return item;
    },
    enabled: !!id,
  });
}

export function useCreateOrchestration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string }) => {
      return invoke<Orchestration>('create_orchestration', { name: data.name });
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
      return invoke<Orchestration>('create_orchestration', { name: data.name || '' });
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
      await invoke('delete_company', { id: _id });
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
      return invoke<OrchestrationRun>('run_orchestration', { id: orchestrationId });
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
      return invoke<OrchestrationRun[]>('list_orchestrations');
    },
  });
}
