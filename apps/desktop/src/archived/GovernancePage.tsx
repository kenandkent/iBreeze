import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatBJTime, formatNumber } from '../../utils/format';
import { X, CheckCircle2, XCircle, Plus, FileText, Wallet, Tag } from 'lucide-react';

// 预算金额在后端以微元整数存储，前端展示需 /1e6 还原为元，表单输入元需 *1e6
const microsToYuan = (m: number | undefined | null): number => (m ? m / 1_000_000 : 0);
const yuanToMicros = (y: number | undefined | null): number => Math.round((y ?? 0) * 1_000_000);

const TABS = [
  { key: 'approval', label: '审批', icon: FileText },
  { key: 'policy', label: '预算策略', icon: Wallet },
  { key: 'type', label: '审批类型', icon: Tag },
] as const;
type TabKey = (typeof TABS)[number]['key'];

interface ApprovalItem {
  approval_id: string;
  company_id: string;
  task_id: string;
  approval_type: string;
  status: string;
  risk_reason?: string;
  requested_by?: string;
  expiry?: string;
  version: number;
}

interface ApprovalDetail {
  approval_id: string;
  company_id: string;
  task_id: string;
  approval_type: string;
  status: string;
  risk_reason?: string;
  requested_by?: string;
  expiry?: string;
  version: number;
  current_limit_micros?: number;
  requested_limit_micros?: number;
  currency?: string;
  [k: string]: unknown;
}

interface PolicyData {
  exists: boolean;
  monthly_limit?: number;
  per_task_limit?: number;
  currency?: string;
  on_budget_exceeded?: string;
  version?: number;
}

interface ApprovalTypeItem {
  approval_type_id: string;
  name: string;
  category: string;
  requires_risk_summary: boolean;
  status: string;
  version: number;
}

export function GovernancePage() {
  const queryClient = useQueryClient();
  const { currentCompanyId } = useAppStore();
  const [tab, setTab] = useState<TabKey>('approval');

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再进入治理与审批。</div>;
  }

  return (
    <div className="p-6">
      <h2 className="text-base font-medium text-gray-700 mb-4">治理与审批</h2>
      <div className="flex gap-2 mb-4">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
                tab === t.key ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'approval' && <ApprovalModule companyId={currentCompanyId} queryClient={queryClient} />}
      {tab === 'policy' && <PolicyModule companyId={currentCompanyId} queryClient={queryClient} />}
      {tab === 'type' && <TypeModule companyId={currentCompanyId} queryClient={queryClient} />}
    </div>
  );
}

function ApprovalModule({ companyId, queryClient }: { companyId: string; queryClient: ReturnType<typeof useQueryClient> }) {
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [resolveTarget, setResolveTarget] = useState<ApprovalItem | null>(null);
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');
  const [comment, setComment] = useState('');
  const [detailTarget, setDetailTarget] = useState<ApprovalItem | null>(null);
  const [showRequest, setShowRequest] = useState(false);
  const [requestForm, setRequestForm] = useState({ approval_type: '', target_ref: '', task_id: '' });

  const { data, isLoading, error, refetch } = useQuery<{ approvals: ApprovalItem[]; total: number }>({
    queryKey: ['approval', companyId, statusFilter, typeFilter],
    queryFn: () =>
      rpcCall<{ approvals: ApprovalItem[]; total: number }>('approval.list', {
        company_id: companyId,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(typeFilter ? { approval_type: typeFilter } : {}),
      }),
    enabled: !!companyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: detail } = useQuery<ApprovalDetail>({
    queryKey: ['approvalDetail', companyId, detailTarget?.approval_id],
    queryFn: () => rpcCall<ApprovalDetail>('approval.get', { approval_id: detailTarget!.approval_id }),
    enabled: !!detailTarget,
  });

  const resolveMutation = useMutation({
    mutationFn: (p: { approval_id: string; decision: 'approve' | 'reject'; comment?: string; expected_version?: number }) =>
      rpcCall('approval.resolve', { approval_id: p.approval_id, decision: p.decision, ...(p.comment ? { comment: p.comment } : {}), ...(p.expected_version !== undefined ? { expected_version: p.expected_version } : {}) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval', companyId] });
      setResolveTarget(null);
      setComment('');
    },
  });

  const requestMutation = useMutation({
    mutationFn: (p: { company_id: string; approval_type: string; target_ref: string; task_id?: string }) =>
      rpcCall('approval.request', { company_id: p.company_id, approval_type: p.approval_type, target_ref: p.target_ref, ...(p.task_id ? { task_id: p.task_id } : {}) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval', companyId] });
      setShowRequest(false);
      setRequestForm({ approval_type: '', target_ref: '', task_id: '' });
    },
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) {
    return (
      <div className="p-2">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  const items = data?.approvals ?? [];

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">状态</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
          >
            <option value="">全部</option>
            <option value="open">open</option>
            <option value="pending">pending</option>
            <option value="resolved">resolved</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">审批类型</label>
          <input
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            placeholder="输入类型筛选"
            className="w-44 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
          />
        </div>
        <button onClick={() => setShowRequest(true)} className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 h-[38px]">
          <Plus className="w-4 h-4" /> 发起审批请求
        </button>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <FileText className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无审批</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">审批 ID</th>
                <th className="px-4 py-2 font-medium">类型</th>
                <th className="px-4 py-2 font-medium">状态</th>
                <th className="px-4 py-2 font-medium">风险原因</th>
                <th className="px-4 py-2 font-medium">过期时间</th>
                <th className="px-4 py-2 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((a) => (
                <tr key={a.approval_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-800 font-mono text-xs">{a.approval_id}</td>
                  <td className="px-4 py-2.5 text-gray-600">{a.approval_type}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={a.status} /></td>
                  <td className="px-4 py-2.5 text-gray-600 max-w-[220px] truncate" title={a.risk_reason}>{a.risk_reason || '-'}</td>
                  <td className="px-4 py-2.5 text-gray-600">{formatBJTime(a.expiry)}</td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => setDetailTarget(a)} className="text-xs text-blue-500 hover:underline mr-3">详情</button>
                    <button
                      onClick={() => { setResolveTarget(a); setDecision('approve'); }}
                      className="text-xs text-green-600 hover:underline"
                    >决议</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 决议弹窗 */}
      {resolveTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setResolveTarget(null)}>
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">审批决议</h3>
              <button onClick={() => setResolveTarget(null)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">决议</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setDecision('approve')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border ${
                      decision === 'approve' ? 'border-green-400 bg-green-50 text-green-700' : 'border-gray-200 text-gray-600'
                    }`}
                  >
                    <CheckCircle2 className="w-4 h-4" /> 通过
                  </button>
                  <button
                    onClick={() => setDecision('reject')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border ${
                      decision === 'reject' ? 'border-red-400 bg-red-50 text-red-700' : 'border-gray-200 text-gray-600'
                    }`}
                  >
                    <XCircle className="w-4 h-4" /> 拒绝
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">备注</label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  placeholder="可选备注"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setResolveTarget(null)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => resolveMutation.mutate({ approval_id: resolveTarget.approval_id, decision, comment: comment || undefined, expected_version: resolveTarget.version })}
                disabled={resolveMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {resolveMutation.isPending ? '提交中...' : '确认决议'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 详情弹窗 */}
      {detailTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setDetailTarget(null)}>
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">审批详情</h3>
              <button onClick={() => setDetailTarget(null)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            {!detail ? (
              <LoadingSpinner text="加载详情..." />
            ) : (
              <div className="space-y-2 text-sm">
                <Row label="审批 ID" value={detail.approval_id} />
                <Row label="类型" value={detail.approval_type} />
                <Row label="状态" value={detail.status} />
                <Row label="任务 ID" value={detail.task_id} />
                <Row label="风险原因" value={detail.risk_reason || '-'} />
                <Row label="过期时间" value={formatBJTime(detail.expiry)} />
                {detail.current_limit_micros !== undefined && (
                  <Row label="当前额度(元)" value={formatNumber(microsToYuan(detail.current_limit_micros))} />
                )}
                {detail.requested_limit_micros !== undefined && (
                  <Row label="申请额度(元)" value={formatNumber(microsToYuan(detail.requested_limit_micros))} />
                )}
                {detail.currency && <Row label="币种" value={detail.currency} />}
              </div>
            )}
            <div className="flex justify-end mt-6">
              <button onClick={() => setDetailTarget(null)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-md">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 发起请求弹窗 */}
      {showRequest && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowRequest(false)}>
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">发起审批请求</h3>
              <button onClick={() => setShowRequest(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">审批类型 <span className="text-red-500">*</span></label>
                <input
                  value={requestForm.approval_type}
                  onChange={(e) => setRequestForm({ ...requestForm, approval_type: e.target.value })}
                  placeholder="如 budget_increase"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">目标引用 <span className="text-red-500">*</span></label>
                <input
                  value={requestForm.target_ref}
                  onChange={(e) => setRequestForm({ ...requestForm, target_ref: e.target.value })}
                  placeholder="如 task_id 或资源引用"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">任务 ID（可选）</label>
                <input
                  value={requestForm.task_id}
                  onChange={(e) => setRequestForm({ ...requestForm, task_id: e.target.value })}
                  placeholder="关联任务 ID"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div className="text-xs text-gray-400">公司 ID: {companyId}</div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowRequest(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => requestForm.approval_type && requestForm.target_ref && requestMutation.mutate({ company_id: companyId, approval_type: requestForm.approval_type, target_ref: requestForm.target_ref, task_id: requestForm.task_id || undefined })}
                disabled={!requestForm.approval_type || !requestForm.target_ref || requestMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {requestMutation.isPending ? '提交中...' : '提交请求'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PolicyModule({ companyId, queryClient }: { companyId: string; queryClient: ReturnType<typeof useQueryClient> }) {
  const [showEdit, setShowEdit] = useState(false);
  const [form, setForm] = useState({ monthly_limit: '', per_task_limit: '', on_budget_exceeded: 'block', reason: '' });

  const { data, isLoading, error, refetch } = useQuery<PolicyData>({
    queryKey: ['budgetPolicy', companyId],
    queryFn: () => rpcCall<PolicyData>('gov.budgetPolicy.get', { company_id: companyId }),
    enabled: !!companyId,
    retry: 2,
    retryDelay: 1000,
  });

  const updateMutation = useMutation({
    mutationFn: (p: { company_id: string; updates: { monthly_limit?: number; per_task_limit?: number; on_budget_exceeded?: string }; reason?: string; expected_policy_version?: number }) =>
      rpcCall('gov.budgetPolicy.update', {
        company_id: p.company_id,
        updates: p.updates,
        ...(p.reason ? { reason: p.reason } : {}),
        ...(p.expected_policy_version !== undefined ? { expected_policy_version: p.expected_policy_version } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetPolicy', companyId] });
      setShowEdit(false);
    },
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) {
    return (
      <div className="p-2">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  const policy = data;
  const openEdit = () => {
    setForm({
      monthly_limit: policy?.monthly_limit !== undefined ? microsToYuan(policy.monthly_limit).toString() : '',
      per_task_limit: policy?.per_task_limit !== undefined ? microsToYuan(policy.per_task_limit).toString() : '',
      on_budget_exceeded: policy?.on_budget_exceeded || 'block',
      reason: '',
    });
    setShowEdit(true);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-700">当前预算策略</h3>
        <button onClick={openEdit} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">编辑策略</button>
      </div>

      {!policy || !policy.exists ? (
        <div className="text-center py-12 text-gray-400">
          <Wallet className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">尚未配置预算策略</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 p-4 grid grid-cols-2 gap-4 text-sm">
          <Row label="月度限额(元)" value={formatNumber(microsToYuan(policy.monthly_limit))} />
          <Row label="单任务限额(元)" value={formatNumber(microsToYuan(policy.per_task_limit))} />
          <Row label="币种" value={policy.currency || '-'} />
          <Row label="超限策略" value={policy.on_budget_exceeded || '-'} />
        </div>
      )}

      {showEdit && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowEdit(false)}>
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">编辑预算策略</h3>
              <button onClick={() => setShowEdit(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">月度限额（元）</label>
                <input
                  type="number"
                  value={form.monthly_limit}
                  onChange={(e) => setForm({ ...form, monthly_limit: e.target.value })}
                  placeholder="0"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">单任务限额（元）</label>
                <input
                  type="number"
                  value={form.per_task_limit}
                  onChange={(e) => setForm({ ...form, per_task_limit: e.target.value })}
                  placeholder="0"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">超限策略</label>
                <select
                  value={form.on_budget_exceeded}
                  onChange={(e) => setForm({ ...form, on_budget_exceeded: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                >
                  <option value="block">block（阻止）</option>
                  <option value="notify">notify（通知）</option>
                  <option value="allow">allow（放行）</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">变更原因</label>
                <input
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  placeholder="可选"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowEdit(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => updateMutation.mutate({
                  company_id: companyId,
                  updates: {
                    monthly_limit: yuanToMicros(parseFloat(form.monthly_limit)),
                    per_task_limit: yuanToMicros(parseFloat(form.per_task_limit)),
                    on_budget_exceeded: form.on_budget_exceeded,
                  },
                  reason: form.reason || undefined,
                  expected_policy_version: policy?.version,
                })}
                disabled={updateMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {updateMutation.isPending ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TypeModule({ companyId, queryClient }: { companyId: string; queryClient: ReturnType<typeof useQueryClient> }) {
  const [categoryFilter, setCategoryFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', category: '', description: '', requires_risk_summary: false });

  const { data, isLoading, error, refetch } = useQuery<{ types: ApprovalTypeItem[] }>({
    queryKey: ['approvalType', companyId, categoryFilter],
    queryFn: () =>
      rpcCall<{ types: ApprovalTypeItem[] }>('gov.approvalType.list', {
        company_id: companyId,
        ...(categoryFilter ? { category: categoryFilter } : {}),
      }),
    enabled: !!companyId,
    retry: 2,
    retryDelay: 1000,
  });

  const createMutation = useMutation({
    mutationFn: (p: { company_id: string; name: string; category: string; description?: string; requires_risk_summary?: boolean }) =>
      rpcCall('gov.approvalType.create', {
        company_id: p.company_id,
        name: p.name,
        category: p.category,
        ...(p.description ? { description: p.description } : {}),
        ...(p.requires_risk_summary !== undefined ? { requires_risk_summary: p.requires_risk_summary } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvalType', companyId] });
      setShowCreate(false);
      setForm({ name: '', category: '', description: '', requires_risk_summary: false });
    },
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) {
    return (
      <div className="p-2">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  const types = data?.types ?? [];

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">分类筛选</label>
          <input
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            placeholder="输入分类"
            className="w-44 px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
          />
        </div>
        <button onClick={() => setShowCreate(true)} className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 h-[38px]">
          <Plus className="w-4 h-4" /> 新建审批类型
        </button>
      </div>

      {types.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Tag className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无审批类型</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">名称</th>
                <th className="px-4 py-2 font-medium">分类</th>
                <th className="px-4 py-2 font-medium">需风险摘要</th>
                <th className="px-4 py-2 font-medium">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {types.map((t) => (
                <tr key={t.approval_type_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-800">{t.name}</td>
                  <td className="px-4 py-2.5 text-gray-600">{t.category}</td>
                  <td className="px-4 py-2.5 text-gray-600">{t.requires_risk_summary ? '是' : '否'}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={t.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">新建审批类型</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">名称 <span className="text-red-500">*</span></label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="如 预算提升"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">分类 <span className="text-red-500">*</span></label>
                <input
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  placeholder="如 budget"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">描述</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={3}
                  placeholder="可选"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={form.requires_risk_summary}
                  onChange={(e) => setForm({ ...form, requires_risk_summary: e.target.checked })}
                  className="w-4 h-4"
                />
                需要风险摘要
              </label>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowCreate(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => form.name && form.category && createMutation.mutate({ company_id: companyId, name: form.name, category: form.category, description: form.description || undefined, requires_risk_summary: form.requires_risk_summary })}
                disabled={!form.name || !form.category || createMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {createMutation.isPending ? '创建中...' : '确认创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-gray-100 pb-1">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-800">{value}</span>
    </div>
  );
}
