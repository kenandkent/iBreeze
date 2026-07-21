import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { useAppStore } from '../../stores/appStore';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { X, Eye, Check, XCircle } from 'lucide-react';
import type { Employee } from '../../types';

// kg 读方法需要模拟查看身份(view_as_employee_id)，写方法无需
interface KgDocument {
  document_id: string;
  title: string;
  source_category: string;
  visibility: string;
  governance_confirmed: boolean;
}

interface KgCitation {
  citation_id: string;
  document_id: string;
  chunk_id: string;
  source_record_id: string;
  locator: string;
  quote_hash: string;
  status: string;
}

export function KnowledgeGovernancePage() {
  const queryClient = useQueryClient();
  const currentCompanyId = useAppStore((s) => s.currentCompanyId);

  // 查看身份:影响所有 kg 读操作
  const [viewAsEmployeeId, setViewAsEmployeeId] = useState<string>('');
  const [sourceCategory, setSourceCategory] = useState<string>('');

  // 文档查看弹窗
  const [viewDoc, setViewDoc] = useState<{
    document_id: string;
    title: string;
    content?: string;
    loading?: boolean;
  } | null>(null);

  // 拒绝弹窗
  const [rejectTarget, setRejectTarget] = useState<KgDocument | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  // 重新索引
  const [reindexSourceId, setReindexSourceId] = useState('');

  // 引文查询
  const [citationId, setCitationId] = useState('');
  const [citationResult, setCitationResult] = useState<KgCitation | null>(null);
  const [citationError, setCitationError] = useState<string | null>(null);

  // 来源删除
  const [deleteSourceType, setDeleteSourceType] = useState('document');
  const [deleteSourceId, setDeleteSourceId] = useState('');
  const [deleteMode, setDeleteMode] = useState<'soft' | 'hard'>('soft');
  const [deleteTarget, setDeleteTarget] = useState<{ source_type: string; source_id: string; mode: string } | null>(null);

  // 摄取重试
  const [retryJobId, setRetryJobId] = useState('');
  const [retryMsg, setRetryMsg] = useState<string | null>(null);

  // 检索
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState<unknown>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  // 员工下拉
  const { data: employees } = useQuery<Employee[]>({
    queryKey: ['org', 'employees', currentCompanyId],
    queryFn: () => rpcCall<Employee[]>('org.employee.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
  });

  // 文档治理列表(读,带 view_as_employee_id)
  const {
    data: documents,
    isLoading,
    error,
  } = useQuery<KgDocument[]>({
    queryKey: ['kg', 'document', 'list', currentCompanyId, viewAsEmployeeId, sourceCategory],
    queryFn: () =>
      rpcCall<{ documents: KgDocument[] }>('kg.document.list', {
        company_id: currentCompanyId,
        view_as_employee_id: viewAsEmployeeId ?? '',
        source_category: sourceCategory || undefined,
      }).then((r) => r.documents),
    enabled: !!currentCompanyId && !!viewAsEmployeeId,
  });

  // 确认治理
  const confirmMutation = useMutation({
    mutationFn: async (doc: KgDocument) =>
      rpcCall('kg.knowledge.confirm', { company_id: currentCompanyId, knowledge_id: doc.document_id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kg', 'document', 'list'] }),
  });

  // 拒绝治理
  const rejectMutation = useMutation({
    mutationFn: async (doc: KgDocument) =>
      rpcCall('kg.knowledge.reject', {
        company_id: currentCompanyId,
        knowledge_id: doc.document_id,
        reason: rejectReason || undefined,
      }),
    onSuccess: () => {
      setRejectTarget(null);
      setRejectReason('');
      queryClient.invalidateQueries({ queryKey: ['kg', 'document', 'list'] });
    },
  });

  // 重新索引
  const reindexMutation = useMutation({
    mutationFn: async () =>
      rpcCall('kg.reindex', {
        company_id: currentCompanyId,
        source_id: reindexSourceId || undefined,
      }),
  });

  // 来源删除
  const deleteSourceMutation = useMutation({
    mutationFn: async (t: { source_type: string; source_id: string; mode: string }) =>
      rpcCall('kg.source.delete', {
        company_id: currentCompanyId,
        source_type: t.source_type,
        source_id: t.source_id,
        mode: t.mode,
      }),
    onSuccess: () => setDeleteTarget(null),
  });

  // 摄取重试
  const retryMutation = useMutation({
    mutationFn: async (jobId: string) =>
      rpcCall('kg.ingest.retry', { company_id: currentCompanyId, job_id: jobId }),
  });

  if (!currentCompanyId) {
    return (
      <div className="p-6">
        <div className="text-sm text-gray-500">请先在顶部选择一个公司后再使用知识治理功能。</div>
      </div>
    );
  }

  const handleViewDoc = async (doc: KgDocument) => {
    setViewDoc({ document_id: doc.document_id, title: doc.title, loading: true });
    try {
      const r = await rpcCall<{ content: string }>('kg.document.get', {
        company_id: currentCompanyId,
        view_as_employee_id: viewAsEmployeeId ?? '',
        knowledge_id: doc.document_id,
      });
      setViewDoc({ document_id: doc.document_id, title: doc.title, content: r.content });
    } catch (e) {
      setViewDoc({ document_id: doc.document_id, title: doc.title, content: `加载失败: ${(e as Error).message}` });
    }
  };

  const handleCitationSearch = async () => {
    if (!citationId.trim()) return;
    setCitationError(null);
    setCitationResult(null);
    try {
      const r = await rpcCall<KgCitation>('kg.citation.get', {
        company_id: currentCompanyId,
        view_as_employee_id: viewAsEmployeeId ?? '',
        citation_id: citationId.trim(),
      });
      setCitationResult(r);
    } catch (e) {
      setCitationError((e as Error).message);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchError(null);
    setSearchResult(null);
    try {
      const r = await rpcCall('kg.search', {
        company_id: currentCompanyId,
        view_as_employee_id: viewAsEmployeeId ?? '',
        query: searchQuery.trim(),
        limit: 20,
      });
      setSearchResult(r);
    } catch (e) {
      setSearchError((e as Error).message);
    }
  };

  const handleRetry = async () => {
    if (!retryJobId.trim()) return;
    setRetryMsg(null);
    try {
      const r = await retryMutation.mutateAsync(retryJobId.trim());
      setRetryMsg(`已提交重试,新任务 ID: ${(r as { new_job_id?: string }).new_job_id ?? '-'}`);
    } catch (e) {
      setRetryMsg(`重试失败: ${(e as Error).message}`);
    }
  };

  return (
    <div className="p-6 space-y-8">
      {/* 顶部:公司上下文 + 查看身份 */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-sm text-gray-600 mb-1">当前公司</label>
          <div className="px-3 py-2 border border-gray-200 rounded-md text-sm bg-gray-50 text-gray-700 w-56">
            {currentCompanyId}
          </div>
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">
            查看身份<span className="text-red-500"> *</span>(view_as_employee_id)
          </label>
          <select
            value={viewAsEmployeeId}
            onChange={(e) => setViewAsEmployeeId(e.target.value)}
            className="w-56 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
          >
            <option value="">请选择员工</option>
            {(employees ?? []).map((emp) => (
              <option key={emp.employee_id} value={emp.employee_id}>
                {emp.name}（{emp.employee_id}）
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">来源分类(可选)</label>
          <input
            type="text"
            value={sourceCategory}
            onChange={(e) => setSourceCategory(e.target.value)}
            className="w-44 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
            placeholder="如 policy"
          />
        </div>
      </div>

      {!viewAsEmployeeId && (
        <div className="text-sm text-amber-600">请选择查看身份,否则无法加载知识治理数据。</div>
      )}

      {/* 文档治理列表 */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-medium text-gray-700">文档治理</h2>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={reindexSourceId}
              onChange={(e) => setReindexSourceId(e.target.value)}
              placeholder="source_id(可选)"
              className="w-40 px-3 py-1.5 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
            />
            <button
              onClick={() => reindexMutation.mutate()}
              disabled={reindexMutation.isPending}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {reindexMutation.isPending ? '索引中...' : '重新索引'}
            </button>
          </div>
        </div>

        {isLoading ? (
          <LoadingSpinner />
        ) : error ? (
          <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        ) : !documents || documents.length === 0 ? (
          <div className="text-sm text-gray-400 py-8 text-center border border-dashed border-gray-200 rounded-lg">
            暂无文档
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">文档 ID</th>
                  <th className="px-4 py-2 font-medium">标题</th>
                  <th className="px-4 py-2 font-medium">来源分类</th>
                  <th className="px-4 py-2 font-medium">可见性</th>
                  <th className="px-4 py-2 font-medium">治理确认</th>
                  <th className="px-4 py-2 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {documents.map((doc) => (
                  <tr key={doc.document_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-2.5 text-gray-500 font-mono text-xs">{doc.document_id}</td>
                    <td className="px-4 py-2.5 font-medium text-gray-800">{doc.title}</td>
                    <td className="px-4 py-2.5 text-gray-600">{doc.source_category}</td>
                    <td className="px-4 py-2.5 text-gray-600">{doc.visibility}</td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={doc.governance_confirmed ? 'active' : 'pending'} />
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleViewDoc(doc)}
                          className="text-gray-400 hover:text-blue-500 p-1"
                          title="查看"
                        >
                          <Eye size={14} />
                        </button>
                        <button
                          onClick={() => confirmMutation.mutate(doc)}
                          disabled={confirmMutation.isPending}
                          className="text-gray-400 hover:text-green-500 p-1 disabled:opacity-40"
                          title="确认"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={() => setRejectTarget(doc)}
                          className="text-gray-400 hover:text-red-500 p-1"
                          title="拒绝"
                        >
                          <XCircle size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 引文查看 */}
      <section>
        <h2 className="text-base font-medium text-gray-700 mb-3">引文查看</h2>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="block text-sm text-gray-600 mb-1">citation_id</label>
            <input
              type="text"
              value={citationId}
              onChange={(e) => setCitationId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
              placeholder="请输入引文 ID"
            />
          </div>
          <button
            onClick={handleCitationSearch}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            查询
          </button>
        </div>
        {citationError && <div className="text-red-500 text-sm mt-2">查询失败: {citationError}</div>}
        {citationResult && (
          <div className="mt-3 bg-white rounded-lg border border-gray-200 p-4 text-sm space-y-1">
            <div><span className="text-gray-500">citation_id: </span>{citationResult.citation_id}</div>
            <div><span className="text-gray-500">document_id: </span>{citationResult.document_id}</div>
            <div><span className="text-gray-500">chunk_id: </span>{citationResult.chunk_id}</div>
            <div><span className="text-gray-500">source_record_id: </span>{citationResult.source_record_id}</div>
            <div><span className="text-gray-500">locator: </span>{citationResult.locator}</div>
            <div><span className="text-gray-500">quote_hash: </span>{citationResult.quote_hash}</div>
            <div><StatusBadge status={citationResult.status} /></div>
          </div>
        )}
      </section>

      {/* 来源删除 */}
      <section>
        <h2 className="text-base font-medium text-gray-700 mb-3">来源删除</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-sm text-gray-600 mb-1">source_type</label>
            <input
              type="text"
              value={deleteSourceType}
              onChange={(e) => setDeleteSourceType(e.target.value)}
              className="w-40 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">source_id</label>
            <input
              type="text"
              value={deleteSourceId}
              onChange={(e) => setDeleteSourceId(e.target.value)}
              className="w-56 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
              placeholder="请输入来源 ID"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">模式</label>
            <select
              value={deleteMode}
              onChange={(e) => setDeleteMode(e.target.value as 'soft' | 'hard')}
              className="w-32 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
            >
              <option value="soft">soft</option>
              <option value="hard">hard</option>
            </select>
          </div>
          <button
            onClick={() => deleteSourceId.trim() && setDeleteTarget({ source_type: deleteSourceType, source_id: deleteSourceId.trim(), mode: deleteMode })}
            disabled={!deleteSourceId.trim()}
            className="px-4 py-2 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
          >
            删除来源
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          来源删除为 LocalOwner 操作,不经过 view_as_employee_id,将直接作用于后端。
        </p>
      </section>

      {/* 摄取重试 */}
      <section>
        <h2 className="text-base font-medium text-gray-700 mb-3">摄取重试</h2>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="block text-sm text-gray-600 mb-1">job_id</label>
            <input
              type="text"
              value={retryJobId}
              onChange={(e) => setRetryJobId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
              placeholder="请输入摄取任务 ID"
            />
          </div>
          <button
            onClick={handleRetry}
            disabled={!retryJobId.trim() || retryMutation.isPending}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {retryMutation.isPending ? '提交中...' : '提交重试'}
          </button>
        </div>
        {retryMsg && <div className="text-sm text-gray-600 mt-2">{retryMsg}</div>}
      </section>

      {/* 检索 */}
      <section>
        <h2 className="text-base font-medium text-gray-700 mb-3">检索</h2>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="block text-sm text-gray-600 mb-1">query</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
              placeholder="请输入检索语句"
            />
          </div>
          <button
            onClick={handleSearch}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            检索
          </button>
        </div>
        {searchError && <div className="text-red-500 text-sm mt-2">检索失败: {searchError}</div>}
        {searchResult != null && (
          <div className="mt-3 bg-white rounded-lg border border-gray-200 p-4 text-sm">
            <pre className="whitespace-pre-wrap break-all text-xs text-gray-700">
              {String(JSON.stringify((searchResult as { result?: unknown; items?: unknown })?.result
                ?? (searchResult as { items?: unknown })?.items
                ?? searchResult, null, 2))}
            </pre>
          </div>
        )}
      </section>

      {/* 文档查看弹窗 */}
      {viewDoc && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setViewDoc(null)}>
          <div className="bg-white rounded-lg p-6 w-[560px] max-h-[80vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">{viewDoc.title}</h3>
              <button onClick={() => setViewDoc(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            {viewDoc.loading ? (
              <LoadingSpinner />
            ) : (
              <pre className="whitespace-pre-wrap break-all text-xs text-gray-700 bg-gray-50 rounded-md p-3 max-h-[60vh] overflow-auto">
                {viewDoc.content ?? '-'}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* 拒绝弹窗 */}
      {rejectTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setRejectTarget(null)}>
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">拒绝治理</h3>
              <button onClick={() => setRejectTarget(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <label className="block text-sm text-gray-600 mb-1">拒绝原因(可选)</label>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-24 resize-none"
              placeholder="请输入拒绝原因"
            />
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setRejectTarget(null)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">
                取消
              </button>
              <button
                onClick={() => rejectTarget && rejectMutation.mutate(rejectTarget)}
                disabled={rejectMutation.isPending}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
              >
                {rejectMutation.isPending ? '拒绝中...' : '确认拒绝'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 来源删除二次确认 */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除来源"
        message={`确定要以 ${deleteTarget?.mode} 模式删除来源「${deleteTarget?.source_type}: ${deleteTarget?.source_id}」吗？此操作不可恢复(若为 hard)。`}
        confirmLabel="确认删除"
        danger
        onConfirm={() => deleteTarget && deleteSourceMutation.mutate(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
