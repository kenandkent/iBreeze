import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime } from '../../utils/format';
import type { Grant } from '../../types';
import { KeyRound, X } from 'lucide-react';

export function GrantPage() {
  const queryClient = useQueryClient();
  const { currentCompanyId } = useAppStore();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    target_type: 'department',
    target_ref: '',
    permission: '',
    expires_at: '',
  });

  const { data: grants, isLoading, error, refetch } = useQuery<Grant[]>({
    queryKey: ['grant', currentCompanyId],
    queryFn: () => rpcCall<Grant[]>('org.grant.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const createMutation = useMutation({
    mutationFn: async (data: typeof form) =>
      rpcCall('org.grant.create', { company_id: currentCompanyId, ...data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['grant', currentCompanyId] });
      setShowCreate(false);
      setForm({ target_type: 'department', target_ref: '', permission: '', expires_at: '' });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (grant: Grant) => rpcCall('org.grant.revoke', { grant_id: grant.grant_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['grant', currentCompanyId] });
    },
  });

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再管理授权。</div>;
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    console.error('[iBreeze] GrantPage: load failed', error);
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium text-gray-700">授权</h2>
        <button onClick={() => setShowCreate(true)} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">新建授权</button>
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">新建授权</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">目标类型</label>
                <select
                  value={form.target_type}
                  onChange={(e) => setForm({ ...form, target_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                >
                  <option value="department">部门</option>
                  <option value="task">任务</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">目标引用</label>
                <input value={form.target_ref} onChange={(e) => setForm({ ...form, target_ref: e.target.value })} placeholder="请输入部门或任务 ID" className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">权限</label>
                <input value={form.permission} onChange={(e) => setForm({ ...form, permission: e.target.value })} placeholder="请输入权限标识" className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">过期时间</label>
                <input type="datetime-local" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowCreate(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => form.target_ref && form.permission && createMutation.mutate(form)}
                disabled={!form.target_ref || !form.permission || createMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {createMutation.isPending ? '创建中...' : '确认创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {!grants || grants.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <KeyRound className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无授权</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">目标类型</th>
                <th className="px-4 py-2 font-medium">目标引用</th>
                <th className="px-4 py-2 font-medium">权限</th>
                <th className="px-4 py-2 font-medium">过期时间</th>
                <th className="px-4 py-2 font-medium">状态</th>
                <th className="px-4 py-2 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {grants.map((g) => (
                <tr key={g.grant_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-600">{g.target_type}</td>
                  <td className="px-4 py-2.5 text-gray-800">{g.target_ref}</td>
                  <td className="px-4 py-2.5 text-gray-600">{g.permission}</td>
                  <td className="px-4 py-2.5 text-gray-600">{formatBJTime(g.expires_at)}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={g.status} /></td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => revokeMutation.mutate(g)} className="text-xs text-red-500 hover:underline">撤销</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
