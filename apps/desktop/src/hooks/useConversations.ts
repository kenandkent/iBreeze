import { useState, useEffect, useCallback } from 'react';
import type { Conversation, Message } from '../types';

export function useConversations(companyId: string) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConversations = useCallback(async () => {
    try {
      setLoading(true);
      // TODO: Implement actual API call via Tauri IPC
      setConversations([]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch conversations');
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  return { conversations, loading, error, refetch: fetchConversations };
}

export function useMessages(conversationId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMessages = useCallback(async () => {
    try {
      setLoading(true);
      // TODO: Implement actual API call via Tauri IPC
      setMessages([]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch messages');
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  return { messages, loading, error, refetch: fetchMessages };
}

export function useSendMessage(conversationId: string) {
  const [sending, setSending] = useState(false);

  const sendMessage = useCallback(async (_content: string) => {
    try {
      setSending(true);
      // TODO: Implement actual API call via Tauri IPC
      return true;
    } catch (e) {
      console.error('Failed to send message:', e);
      return false;
    } finally {
      setSending(false);
    }
  }, [conversationId]);

  return { sendMessage, sending };
}
