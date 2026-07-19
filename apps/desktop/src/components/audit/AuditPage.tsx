import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime } from '../../utils/format';
import type { AuditEntry, AuditType } from '../../types';
import { ScrollText } from 'lucide-react';

const PAGE_SIZE = 10;

const AUDIT_TABS: { key: AuditType; label: string }[] = [
  { key: 'acl', label: '访问控制' },
  { key: 'org', label: '组织' },
  { key: 'governance', label: '治理' },
];

export function AuditPage() {
  const { currentCompanyId } = useAppStore();
  const [auditType, setAuditType] = useState<AuditType>('acl');
  const [page, setPage] = useState(1);

  const { data, isLoading, error, refetch } = useQuery<{ items: AuditEntry[]; total: number }>({
    queryKey: ['audit', currentCompanyId, auditType, page],
    queryFn: () =>
      rpcCall<{ items: AuditEntry[]; total: number }>('audit.query', {
        company_id: currentCompanyId,
        audit_type: auditType,
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看审计日志。</div>;
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    console.error('[iBreeze] AuditPage: load failed', error);
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
      <h2 className="text-base font-medium text-gray-700 mb-4">审计</h2>
      <div className="flex gap-2 mb-4">
        {AUDIT_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => { setAuditType(tab.key); setPage(1); }}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              auditType === tab.key ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <ScrollText className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无审计记录</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">时间</th>
                <th className="px-4 py-2 font-medium">操作</th>
                <th className="px-4 py-2 font-medium">资源</th>
                <th className="px-4 py-2 font-medium">结果</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((a) => (
                <tr key={a.audit_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-600">{formatBJTime(a.created_at)}</td>
                  <td className="px-4 py-2.5 text-gray-800">{a.action}</td>
                  <td className="px-4 py-2.5 text-gray-600">{a.resource}</td>
                  <td className="px-4 py-2.5 text-gray-600">{a.result}</td>
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
