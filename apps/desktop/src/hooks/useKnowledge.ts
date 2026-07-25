import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { KnowledgeEntry } from '../types';
import { logger } from '../utils/logger';

export function useListKnowledgeEntries() {
  return useQuery({
    queryKey: ['knowledge'],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry[]>('rpc_request', { method: 'knowledge.list', params: {} });
        logger.logHookSuccess('useKnowledge', 'knowledge.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useSearchKnowledge(query: string) {
  return useQuery({
    queryKey: ['knowledge', 'search', query],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry[]>('rpc_request', { method: 'knowledge.search', params: { query } });
        logger.logHookSuccess('useKnowledge', 'knowledge.search', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.search', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: query.length > 0,
  });
}

export function useCreateKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { title: string; content: string; type: string; tags?: string[] }) => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry>('rpc_request', { method: 'knowledge.import', params: { data } });
        logger.logHookSuccess('useKnowledge', 'knowledge.import', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.import', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}

export function useUpdateKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; title?: string; content?: string; type?: string; tags?: string[] }) => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry>('rpc_request', { method: 'knowledge.import', params: { data } });
        logger.logHookSuccess('useKnowledge', 'knowledge.update', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.update', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}

export function useArchiveKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'knowledge.remove', params: { id: _id } });
        logger.logHookSuccess('useKnowledge', 'knowledge.remove', performance.now() - start);
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.remove', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}
