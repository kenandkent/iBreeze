import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { KnowledgeEntry } from '../types';

export function useListKnowledgeEntries() {
  return useQuery({
    queryKey: ['knowledge'],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      return invoke<KnowledgeEntry[]>('list_knowledge_entries');
    },
  });
}

export function useSearchKnowledge(query: string) {
  return useQuery({
    queryKey: ['knowledge', 'search', query],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      return invoke<KnowledgeEntry[]>('search_knowledge', { query });
    },
    enabled: query.length > 0,
  });
}

export function useCreateKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { title: string; content: string; type: string; tags?: string[] }) => {
      return invoke<KnowledgeEntry>('create_knowledge_entry', { data });
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
      return invoke<KnowledgeEntry>('create_knowledge_entry', { data });
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
      await invoke('delete_company', { id: _id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });
}
