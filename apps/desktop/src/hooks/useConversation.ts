import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Conversation, Message } from '../types';

// 列出对话
export function useListConversations(companyId: string) {
  return useQuery({
    queryKey: ['conversations', companyId],
    queryFn: async (): Promise<Conversation[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC conversation.list
      return [];
    },
    enabled: !!companyId,
  });
}

// 获取单个对话详情
export function useGetConversation(id: string) {
  return useQuery({
    queryKey: ['conversations', id],
    queryFn: async (): Promise<Conversation> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC conversation.get
      throw new Error('Not implemented');
    },
    enabled: !!id,
  });
}

// 获取消息列表
export function useListMessages(conversationId: string) {
  return useQuery({
    queryKey: ['messages', conversationId],
    queryFn: async (): Promise<Message[]> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC conversation.messages
      return [];
    },
    enabled: !!conversationId,
  });
}

// 创建对话
export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { company_id: string; title?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC conversation.create
      return {
        id: crypto.randomUUID(),
        company_id: data.company_id,
        title: data.title || '新对话',
        status: 'active',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Conversation;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['conversations', variables.company_id] });
    },
  });
}

// 归档对话
export function useArchiveConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC conversation.archive
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

// 发送消息
export function useAddMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { conversation_id: string; content: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC conversation.addMessage
      return {
        id: crypto.randomUUID(),
        conversation_id: data.conversation_id,
        role: 'user',
        content: data.content,
        created_at: new Date().toISOString(),
      };
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['messages', variables.conversation_id] });
    },
  });
}
