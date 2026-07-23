import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { AgentInfo } from '../types';

// 列出 Agent
export function useListAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: async (): Promise<AgentInfo[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC agent.list
      return [];
    },
    refetchInterval: 5000,
  });
}

// 获取 Agent 状态
export function useGetAgentStatus(id: string) {
  return useQuery({
    queryKey: ['agents', id],
    queryFn: async (): Promise<AgentInfo> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC agent.status
      throw new Error('Not implemented');
    },
    enabled: !!id,
    refetchInterval: 5000,
  });
}

// 运行 Agent
export function useRunAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_data: { agent_id: string; message: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC agent.run
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

// 停止 Agent
export function useStopAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_agentId: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC agent.stop
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}
