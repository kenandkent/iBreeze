import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { useAppStore } from '../../stores/appStore';
import type { Task } from '../../types';
import { ClipboardList, X, Plus, Play, Ban } from 'lucide-react';

const COLUMNS = [
  { key: 'created', label: '待处理' },
  { key: 'running', label: '进行中' },
  { key: 'completed', label: '已完成' },
];

export function TaskBoard() {
  const queryClient = useQueryClient();
  const { currentCompanyId } = useAppStore();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 5 });
  const [cancelTarget, setCancelTarget] = useState<Task | null>(null);

  const { data, isLoading, error, refetch } = useQuery<Task[]>({
    queryKey: ['tasks', currentCompanyId],
    queryFn: () => rpcCall<Task[]>('task.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 3,
    retryDelay: 1000,
  });

  const createMutation = useMutation({
    mutationFn: async (data: typeof form) => rpcCall('task.create', { ...data, company_id: currentCompanyId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks', currentCompanyId] });
      setShowCreate(false);
      setForm({ title: '', description: '', priority: 5 });
    },
  });

  const startMutation = useMutation({
    mutationFn: async (task: Task) => rpcCall('task.start', {
      task_id: task.task_id,
      expected_version: task.version,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks', currentCompanyId] }),
  });

  const cancelMutation = useMutation({
    mutationFn: async (task: Task) => rpcCall('task.cancel', {
      task_id: task.task_id,
      expected_version: task.version,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks', currentCompanyId] });
      setCancelTarget(null);
    },
  });

  if (!currentCompanyId) {
    return (
      <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看任务。</div>
    );
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
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

  const tasks = data ?? [];

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium text-gray-700">任务看板</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          <Plus size={14} />
          新建任务
        </button>
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">新建任务</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">任务标题</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                  placeholder="请输入任务标题"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">优先级</label>
                <select
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                >
                  <option value={1}>P1 - 最高</option>
                  <option value={2}>P2 - 高</option>
                  <option value={3}>P3 - 中高</option>
                  <option value={4}>P4 - 中</option>
                  <option value={5}>P5 - 普通</option>
                  <option value={6}>P6 - 低</option>
                  <option value={7}>P7 - 最低</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">描述</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-24 resize-none"
                  placeholder="请输入任务描述（可选）"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800"
              >
                取消
              </button>
              <button
                onClick={() => createMutation.mutate(form)}
                disabled={!form.title || createMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {createMutation.isPending ? '创建中...' : '确认创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {tasks.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <ClipboardList className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无任务</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {COLUMNS.map((col) => {
            const colTasks = tasks.filter((t) => t.status === col.key);
            return (
              <div key={col.key} className="bg-gray-100 rounded-lg p-3">
                <h3 className="text-sm font-medium text-gray-600 mb-2">
                  {col.label}
                  <span className="ml-1 text-gray-400">({colTasks.length})</span>
                </h3>
                <div className="space-y-2">
                  {colTasks.map((t) => (
                    <div
                      key={t.task_id}
                      className="bg-white rounded-md p-3 border border-gray-200 shadow-sm"
                    >
                      <p className="text-sm font-medium text-gray-800 mb-1">{t.title}</p>
                      {t.description && (
                        <p className="text-xs text-gray-500 mb-2 line-clamp-2">{t.description}</p>
                      )}
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">P{t.priority}</span>
                        <div className="flex items-center gap-1">
                          <StatusBadge status={t.status} />
                          {t.status === 'created' && (
                            <button
                              onClick={() => startMutation.mutate(t)}
                              className="text-green-500 hover:text-green-700 p-0.5"
                              title="开始任务"
                            >
                              <Play size={12} />
                            </button>
                          )}
                          {(t.status === 'created' || t.status === 'running') && (
                            <button
                              onClick={() => setCancelTarget(t)}
                              className="text-red-400 hover:text-red-600 p-0.5"
                              title="取消任务"
                            >
                              <Ban size={12} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={!!cancelTarget}
        title="确认取消"
        message={`确定要取消任务「${cancelTarget?.title}」吗？`}
        confirmLabel="取消任务"
        onConfirm={() => cancelTarget && cancelMutation.mutate(cancelTarget)}
        onCancel={() => setCancelTarget(null)}
      />
    </div>
  );
}
