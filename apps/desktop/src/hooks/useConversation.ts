import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Conversation, Message } from '../types';
import { logger } from '../utils/logger';

export function useListConversations(companyId: string) {
  return useQuery({
    queryKey: ['conversations', companyId],
    queryFn: async (): Promise<Conversation[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Conversation[]>('rpc_request', { method: 'conversation.list', params: { company_id: companyId } });
        logger.logHookSuccess('useConversation', 'conversation.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.list', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId,
  });
}

export function useGetConversation(companyId: string, conversationId: string) {
  return useQuery({
    queryKey: ['conversations', conversationId],
    queryFn: async (): Promise<Conversation> => {
      const start = performance.now();
      try {
        const result = await invoke<Conversation>('rpc_request', { method: 'conversation.getCompany', params: { company_id: companyId } });
        logger.logHookSuccess('useConversation', 'conversation.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!conversationId,
  });
}

export function useListMessages(companyId: string, conversationId: string) {
  return useQuery({
    queryKey: ['messages', conversationId],
    queryFn: async (): Promise<{ items: Message[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const result = await invoke<{ items: Message[]; next_cursor: string | null; has_more: boolean }>(
          'rpc_request',
          { method: 'conversation.listMessages', params: { company_id: companyId, conversation_id: conversationId, cursor: null, limit: 50 } },
        );
        logger.logHookSuccess('useConversation', 'conversation.listMessages', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.listMessages', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!conversationId,
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { company_id: string; title: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Conversation>('rpc_request', { method: 'conversation.create', params: { company_id: data.company_id, title: data.title } });
        logger.logHookSuccess('useConversation', 'conversation.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

export function useArchiveConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; conversation_id: string }) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'conversation.archive', params: { company_id: params.company_id, conversation_id: params.conversation_id } });
        logger.logHookSuccess('useConversation', 'conversation.archive', performance.now() - start);
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.archive', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

export function useAddMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { company_id: string; conversationId: string; content: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Message>('rpc_request', {
          method: 'conversation.submitUserMessage',
          params: {
            company_id: data.company_id,
            conversation_id: data.conversationId,
            content: data.content,
          },
        });
        logger.logHookSuccess('useConversation', 'conversation.submitUserMessage', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.submitUserMessage', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['messages', variables.conversationId] });
    },
  });
}
