import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime } from '../../utils/format';
import type { SessionThread, SessionMessage } from '../../types';
import { MessageSquare, Send } from 'lucide-react';

export function SessionPage() {
  const queryClient = useQueryClient();
  const { currentCompanyId } = useAppStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const { data: threads, isLoading, error, refetch } = useQuery<SessionThread[]>({
    queryKey: ['session', currentCompanyId],
    queryFn: () => rpcCall<SessionThread[]>('session.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: transcript, isLoading: txLoading } = useQuery<SessionMessage[]>({
    queryKey: ['sessionTranscript', selectedId],
    queryFn: () => rpcCall<SessionMessage[]>('session.transcript.get', { thread_id: selectedId }),
    enabled: !!selectedId,
  });

  const sendMutation = useMutation({
    mutationFn: async (content: string) =>
      rpcCall('session.sendMessage', { thread_id: selectedId, content }),
    onSuccess: () => {
      setDraft('');
      queryClient.invalidateQueries({ queryKey: ['sessionTranscript', selectedId] });
    },
  });

  if (!currentCompanyId) {
    return (
      <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看会话。</div>
    );
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    console.error('[iBreeze] SessionPage: load failed', error);
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          重试
        </button>
      </div>
    );
  }

  const selected = threads?.find((t) => t.thread_id === selectedId);

  return (
    <div className="p-6">
      <h2 className="text-base font-medium text-gray-700 mb-4">会话</h2>
      {!threads || threads.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <MessageSquare className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无会话</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">状态</th>
                  <th className="px-4 py-2 font-medium">创建时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {threads.map((t) => (
                  <tr
                    key={t.thread_id}
                    onClick={() => setSelectedId(t.thread_id)}
                    className={`cursor-pointer hover:bg-gray-50 ${selectedId === t.thread_id ? 'bg-blue-50' : ''}`}
                  >
                    <td className="px-4 py-2.5"><StatusBadge status={t.status} /></td>
                    <td className="px-4 py-2.5 text-gray-600">{formatBJTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="col-span-2 bg-white rounded-lg border border-gray-200 p-4 flex flex-col">
            {selected ? (
              <>
                <div className="mb-3 text-sm text-gray-600">
                  安全上下文: {Object.keys(selected.security_context || {}).length
                    ? JSON.stringify(selected.security_context)
                    : '无'}
                </div>
                <div className="flex-1 space-y-2 overflow-auto max-h-80">
                  {txLoading ? (
                    <LoadingSpinner />
                  ) : !transcript || transcript.length === 0 ? (
                    <p className="text-sm text-gray-400">暂无消息记录</p>
                  ) : (
                    transcript.map((m) => (
                      <div key={m.message_id} className="text-sm">
                        <span className="font-medium text-gray-700">{m.role}: </span>
                        <span className="text-gray-600">{m.content}</span>
                      </div>
                    ))
                  )}
                </div>
                <div className="flex gap-2 mt-3">
                  <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="输入消息..."
                    className="flex-1 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                  />
                  <button
                    onClick={() => draft.trim() && sendMutation.mutate(draft.trim())}
                    disabled={!draft.trim() || sendMutation.isPending}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                  >
                    <Send size={14} /> 发送
                  </button>
                </div>
              </>
            ) : (
              <p className="text-sm text-gray-400 m-auto">请选择一个会话线程</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
