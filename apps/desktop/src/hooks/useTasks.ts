import { useState, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import type { Message } from '../types';

export function useSendMessage(conversationId: string) {
  const [sending, setSending] = useState(false);

  const sendMessage = useCallback(async (content: string) => {
    try {
      setSending(true);
      await invoke<Message>('add_message', {
        conversationId,
        content,
        role: 'user',
      });
      return true;
    } catch (e) {
      console.error('发送消息失败:', e);
      return false;
    } finally {
      setSending(false);
    }
  }, [conversationId]);

  return { sendMessage, sending };
}
