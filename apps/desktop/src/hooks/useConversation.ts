import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Conversation, Message } from '../types';
import { logger } from '../utils/logger';

export function useListConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: async (): Promise<Conversation[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Conversation[]>('rpc_request', { method: 'conversation.list', params: {} });
        logger.logHookSuccess('useConversation', 'conversation.list', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.list', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useGetConversation(id: string) {
  return useQuery({
    queryKey: ['conversations', id],
    queryFn: async (): Promise<Conversation> => {
      const start = performance.now();
      try {
        const result = await invoke<Conversation>('rpc_request', { method: 'conversation.get', params: { id } });
        logger.logHookSuccess('useConversation', 'conversation.get', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.get', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!id,
  });
}

export function useListMessages(conversationId: string) {
  return useQuery({
    queryKey: ['messages', conversationId],
    queryFn: async (): Promise<Message[]> => {
      const start = performance.now();
      try {
        const result = await invoke<Message[]>('rpc_request', { method: 'conversation.listMessages', params: { conversationId } });
        logger.logHookSuccess('useConversation', 'conversation.listMessages', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.listMessages', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!conversationId,
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { title: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Conversation>('rpc_request', { method: 'conversation.create', params: { title: data.title } });
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
    mutationFn: async (id: string) => {
      const start = performance.now();
      try {
        await invoke('rpc_request', { method: 'conversation.archive', params: { id } });
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
    mutationFn: async (data: { conversationId: string; content: string; role: string }) => {
      const start = performance.now();
      try {
        const result = await invoke<Message>('rpc_request', {
          method: 'conversation.submitUserMessage',
          params: {
            conversationId: data.conversationId,
            content: data.content,
            role: data.role,
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
