import { useState } from 'react';
import type { Message } from '../types';

interface ChatPanelProps {
  messages: Message[];
  onSendMessage: (content: string) => Promise<boolean>;
  sending: boolean;
}

export function ChatPanel({ messages, onSendMessage, sending }: ChatPanelProps) {
  const [input, setInput] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;

    const success = await onSendMessage(input);
    if (success) {
      setInput('');
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[70%] p-3 rounded-lg ${msg.role === 'user' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>
              {msg.content}
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="p-4 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            className="flex-1 p-2 border rounded"
            disabled={sending}
          />
          <button type="submit" disabled={sending} className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50">
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
