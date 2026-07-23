import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { KnowledgeEntry } from '../types';

// 列出知识条目
interface KnowledgeListParams {
  search?: string;
  type?: string;
  status?: string;
  cursor?: string;
  limit?: number;
}

export function useListKnowledgeEntries(params: KnowledgeListParams = {}) {
  return useQuery({
    queryKey: ['knowledge', params],
    queryFn: async (): Promise<{ data: KnowledgeEntry[]; total: number; next_cursor?: string }> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC knowledge.list
      return { data: [], total: 0 };
    },
  });
}

// 搜索知识条目
export function useSearchKnowledge(query: string) {
  return useQuery({
    queryKey: ['knowledge', 'search', query],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC knowledge.search
      return [];
    },
    enabled: query.length > 0,
  });
}

// 创建知识条目
export function useCreateKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      title: string;
      content: string;
      type: KnowledgeEntry['type'];
      tags?: string[];
    }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC knowledge.create
      return {
        id: crypto.randomUUID(),
        ...data,
        tags: data.tags || [],
        content_hash: '',
        status: 'active' as const,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}

// 更新知识条目
export function useUpdateKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      id: string;
      title?: string;
      content?: string;
      type?: KnowledgeEntry['type'];
      tags?: string[];
    }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC knowledge.update
      return { ...data, updated_at: new Date().toISOString() };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}

// 归档知识条目
export function useArchiveKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC knowledge.archive
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}
