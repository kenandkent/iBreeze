import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Conversation, Message } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListConversations(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.conversationList(ctx, companyId),
    queryFn: async (): Promise<Conversation[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Conversation[]>('conversation.list', { company_id: companyId });
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
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.conversation(ctx, companyId, conversationId),
    queryFn: async (): Promise<Conversation> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Conversation>('conversation.getCompany', { company_id: companyId });
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
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.messageList(ctx, companyId, conversationId),
    queryFn: async (): Promise<{ items: Message[]; next_cursor: string | null; has_more: boolean }> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<{ items: Message[]; next_cursor: string | null; has_more: boolean }>(
          'conversation.listMessages',
          { company_id: companyId, conversation_id: conversationId, cursor: null, limit: 50 },
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
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (data: { company_id: string; title: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Conversation>('conversation.create', { company_id: data.company_id, title: data.title });
        logger.logHookSuccess('useConversation', 'conversation.create', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.create', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}

export function useArchiveConversation() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; conversation_id: string }) => {
      const start = performance.now();
      try {
        await createRpcRequest('conversation.archive', { company_id: params.company_id, conversation_id: params.conversation_id });
        logger.logHookSuccess('useConversation', 'conversation.archive', performance.now() - start);
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.archive', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}

export function useAddMessage() {
  const queryClient = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (data: { company_id: string; conversationId: string; content: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<Message>('conversation.submitUserMessage', {
          company_id: data.company_id,
          conversation_id: data.conversationId,
          content: data.content,
        });
        logger.logHookSuccess('useConversation', 'conversation.submitUserMessage', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useConversation', 'conversation.submitUserMessage', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.all(ctx) });
    },
  });
}
