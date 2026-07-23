import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { Conversation, Message } from '../types';

export function useListConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: async (): Promise<Conversation[]> => {
      return invoke<Conversation[]>('list_conversations');
    },
  });
}

export function useGetConversation(id: string) {
  return useQuery({
    queryKey: ['conversations', id],
    queryFn: async (): Promise<Conversation> => {
      return invoke<Conversation>('get_conversation', { id });
    },
    enabled: !!id,
  });
}

export function useListMessages(conversationId: string) {
  return useQuery({
    queryKey: ['messages', conversationId],
    queryFn: async (): Promise<Message[]> => {
      return invoke<Message[]>('list_messages', { conversationId });
    },
    enabled: !!conversationId,
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { title: string }) => {
      return invoke<Conversation>('create_conversation', { title: data.title });
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
      await invoke('archive_conversation', { id });
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
      return invoke<Message>('add_message', {
        conversationId: data.conversationId,
        content: data.content,
        role: data.role,
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['messages', variables.conversationId] });
    },
  });
}
