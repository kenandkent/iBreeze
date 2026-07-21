import { useQuery } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime } from '../../utils/format';
import type { Task, SessionThread } from '../../types';
import { ClipboardList, MessageSquare, CheckCircle2 } from 'lucide-react';

export function DashboardPage() {
  const { currentCompanyId } = useAppStore();

  const { data: tasks } = useQuery<Task[]>({
    queryKey: ['dashboardTasks', currentCompanyId],
    queryFn: () => rpcCall<Task[]>('task.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: sessions } = useQuery<SessionThread[]>({
    queryKey: ['dashboardSessions', currentCompanyId],
    queryFn: async () => {
      const res = await rpcCall<{ threads: SessionThread[]; total: number }>('session.list', { company_id: currentCompanyId });
      return res.threads ?? [];
    },
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看概览。</div>;
  }

  const activeSessions = (sessions ?? []).filter((s) => s.status === 'active').length;
  const activeTasks = (tasks ?? []).filter((t) => t.status === 'in_progress' || t.status === 'active').length;
  const completedTasks = (tasks ?? []).filter((t) => t.status === 'completed' || t.status === 'done').length;

  const cards = [
    { label: '活跃会话', value: activeSessions, icon: <MessageSquare size={18} /> },
    { label: '进行中任务', value: activeTasks, icon: <ClipboardList size={18} /> },
    { label: '已完成任务', value: completedTasks, icon: <CheckCircle2 size={18} /> },
  ];

  return (
    <div className="p-6">
      <h2 className="text-base font-medium text-gray-700 mb-4">Dashboard</h2>
      <div className="grid grid-cols-3 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-3">
            <div className="text-blue-500">{c.icon}</div>
            <div>
              <div className="text-2xl font-semibold text-gray-800">{c.value}</div>
              <div className="text-xs text-gray-500">{c.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-600 mb-2">最近会话</h3>
          {(sessions ?? []).length === 0 ? (
            <p className="text-sm text-gray-400">暂无会话</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {(sessions ?? []).slice(0, 5).map((s) => (
                <li key={s.thread_id} className="text-gray-700">
                  {s.status} · {formatBJTime(s.created_at)}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-600 mb-2">进行中任务</h3>
          {(tasks ?? []).filter((t) => t.status === 'in_progress' || t.status === 'active').length === 0 ? (
            <p className="text-sm text-gray-400">暂无进行中任务</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {(tasks ?? []).filter((t) => t.status === 'in_progress' || t.status === 'active').slice(0, 5).map((t) => (
                <li key={t.task_id} className="text-gray-700">{t.title}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
