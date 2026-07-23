import { useQuery } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Conversation, Message } from '../types';

export function useConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: async (): Promise<Conversation[]> => {
      return invoke<Conversation[]>('list_conversations');
    },
  });
}

export function useMessages(conversationId: string) {
  return useQuery({
    queryKey: ['messages', conversationId],
    queryFn: async (): Promise<Message[]> => {
      return invoke<Message[]>('list_messages', { conversationId });
    },
    enabled: !!conversationId,
  });
}
