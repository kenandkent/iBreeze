import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime } from '../../utils/format';
import type { Intervention } from '../../types';
import { AlertTriangle } from 'lucide-react';

const PAGE_SIZE = 10;

export function InterventionPage() {
  const { currentCompanyId } = useAppStore();
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading, error, refetch } = useQuery<{ items: Intervention[]; total: number }>({
    queryKey: ['intervention', currentCompanyId, status, page],
    queryFn: () =>
      rpcCall<{ items: Intervention[]; total: number }>('intervention.list', {
        company_id: currentCompanyId,
        status: status || undefined,
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
    retry: 3,
    retryDelay: 1000,
  });

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看人工干预。</div>;
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  const items = data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium text-gray-700">人工干预</h2>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="px-3 py-1.5 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[34px]"
        >
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="resolved">已解决</option>
        </select>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <AlertTriangle className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无人工干预</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">原因</th>
                <th className="px-4 py-2 font-medium">目标引用</th>
                <th className="px-4 py-2 font-medium">状态</th>
                <th className="px-4 py-2 font-medium">创建时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((it) => (
                <tr key={it.intervention_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-800">{it.reason}</td>
                  <td className="px-4 py-2.5 text-gray-600">{it.target_ref}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={it.status} /></td>
                  <td className="px-4 py-2.5 text-gray-600">{formatBJTime(it.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-end gap-3 mt-3 text-sm">
        <button
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
          className="px-3 py-1 border border-gray-200 rounded-md disabled:opacity-40 hover:bg-gray-50"
        >
          上一页
        </button>
        <span className="text-gray-600">第 {page} / {totalPages} 页</span>
        <button
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
          className="px-3 py-1 border border-gray-200 rounded-md disabled:opacity-40 hover:bg-gray-50"
        >
          下一页
        </button>
      </div>
    </div>
  );
}
