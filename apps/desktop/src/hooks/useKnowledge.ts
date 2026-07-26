import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { KnowledgeEntry } from '../types';
import { logger } from '../utils/logger';

export function useListKnowledgeEntries(companyId: string) {
  return useQuery({
    queryKey: ['knowledge', companyId],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry[]>('rpc_request', { method: 'knowledge.list', params: { company_id: companyId } });
        logger.logHookSuccess('useKnowledge', 'knowledge.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useSearchKnowledge(companyId: string, query: string) {
  return useQuery({
    queryKey: ['knowledge', 'search', companyId, query],
    queryFn: async (): Promise<KnowledgeEntry[]> => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry[]>('rpc_request', { method: 'knowledge.search', params: { company_id: companyId, query } });
        logger.logHookSuccess('useKnowledge', 'knowledge.search', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useKnowledge', 'knowledge.search', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && query.length > 0,
  });
}

export function useCreateKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      company_id: string;
      title: string;
      content: string;
      visibility?: string;
      source_artifact_id?: string;
      source_message_event_id?: string;
      owner_employee_id?: string;
      department_id?: string;
      task_id?: string;
    }) => {
      const start = performance.now();
      try {
        const result = await invoke<KnowledgeEntry>('rpc_request', {
          method: 'knowledge.import',
          params: {
            company_id: data.company_id,
            title: data.title,
            content: data.content,
            visibility: data.visibility ?? 'company',
            source_artifact_id: data.source_artifact_id,
            source_message_event_id: data.source_message_event_id,
            owner_employee_id: data.owner_employee_id,
            department_id: data.department_id,
            task_id: data.task_id,
          },
        });
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

export function useArchiveKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; item_id: string }) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'knowledge.remove', params: { company_id: params.company_id, item_id: params.item_id } });
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
