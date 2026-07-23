import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { AgentInfo } from '../types';

export function useListAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: async (): Promise<AgentInfo[]> => {
      return invoke<AgentInfo[]>('list_agents');
    },
    refetchInterval: 5000,
  });
}

export function useRunAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { agent_id: string; message: string }) => {
      return invoke('run_agent', { agentId: data.agent_id, message: data.message });
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
      await invoke('stop_agent', { agentId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}
