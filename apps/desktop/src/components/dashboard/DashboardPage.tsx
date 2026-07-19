import { useQuery } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime } from '../../utils/format';
import type { Company, Employee, Task, KnowledgeDocument, Backend, SessionThread, Intervention } from '../../types';
import { Building2, Users, ClipboardList, BookOpen, Server, AlertTriangle } from 'lucide-react';

export function DashboardPage() {
  const { currentCompanyId } = useAppStore();

  const { data: companies } = useQuery<Company[]>({
    queryKey: ['dashboardCompanies'],
    queryFn: () => rpcCall<Company[]>('company.list'),
    retry: 2,
    retryDelay: 1000,
  });

  const { data: employees } = useQuery<Employee[]>({
    queryKey: ['dashboardEmployees', currentCompanyId],
    queryFn: () => rpcCall<Employee[]>('employee.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: tasks } = useQuery<Task[]>({
    queryKey: ['dashboardTasks', currentCompanyId],
    queryFn: () => rpcCall<Task[]>('task.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: docs } = useQuery<KnowledgeDocument[]>({
    queryKey: ['dashboardDocs', currentCompanyId],
    queryFn: () => rpcCall<KnowledgeDocument[]>('knowledge.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: backends } = useQuery<Backend[]>({
    queryKey: ['dashboardBackends', currentCompanyId],
    queryFn: () => rpcCall<Backend[]>('backend.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: sessions } = useQuery<SessionThread[]>({
    queryKey: ['dashboardSessions', currentCompanyId],
    queryFn: () => rpcCall<SessionThread[]>('session.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: interventions } = useQuery<{ items: Intervention[]; total: number }>({
    queryKey: ['dashboardInterventions', currentCompanyId],
    queryFn: () =>
      rpcCall<{ items: Intervention[]; total: number }>('intervention.list', {
        company_id: currentCompanyId,
        status: 'pending',
        offset: 0,
        limit: 1,
      }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看概览。</div>;
  }

  const activeBackends = (backends ?? []).filter((b) => b.status === 'active').length;
  const pendingInterventions = interventions?.total ?? 0;

  const cards = [
    { label: '公司数', value: (companies ?? []).length, icon: <Building2 size={18} /> },
    { label: '员工数', value: (employees ?? []).length, icon: <Users size={18} /> },
    { label: '进行中任务', value: (tasks ?? []).filter((t) => t.status === 'in_progress' || t.status === 'active').length, icon: <ClipboardList size={18} /> },
    { label: '知识文档数', value: (docs ?? []).length, icon: <BookOpen size={18} /> },
    { label: '活跃 Backend', value: activeBackends, icon: <Server size={18} /> },
    { label: '待处理干预', value: pendingInterventions, icon: <AlertTriangle size={18} /> },
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
