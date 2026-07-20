import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { useAppStore } from '../../stores/appStore';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { formatBJTime } from '../../utils/format';
import type { Task } from '../../types';
import { CheckCircle2, RefreshCw, ShieldCheck, ListChecks, Inbox, X } from 'lucide-react';

// 节点结构（来自 task.nodes）
interface TaskNode {
  node_id: string;
  node_type: string;
  goal: string;
  status: string;
  depends_on: string[];
  assignee_employee_id: string | null;
  generation_id: string | null;
  version: number;
}

// 校验计划返回
interface ValidateResult {
  ok: boolean;
  rule?: string;
  error?: string;
}

// 检查点返回（结构容错）
type CheckpointList = unknown[];

// 死信解决返回
interface DeadLetterResolve {
  dead_letter_id: string;
  status: string;
}

export function TaskAdvancedPage() {
  const currentCompanyId = useAppStore((s) => s.currentCompanyId);
  const queryClient = useQueryClient();

  // 选中的任务（用于检查点 / 节点操作）
  const [selectedTaskId, setSelectedTaskId] = useState<string>('');

  if (!currentCompanyId) {
    return (
      <div className="p-6">
        <div className="text-center py-12 text-gray-400">
          <p className="text-sm">请先在左侧选择公司后再进行操作</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8">
      <h2 className="text-base font-medium text-gray-700">任务高级操作 / 工作流</h2>

      <TaskOperationSection
        companyId={currentCompanyId}
        queryClient={queryClient}
        selectedTaskId={selectedTaskId}
        setSelectedTaskId={setSelectedTaskId}
      />

      <CheckpointSection companyId={currentCompanyId} selectedTaskId={selectedTaskId} />

      <DeadLetterSection />
    </div>
  );
}

/* ===================== 1. 任务操作分区 ===================== */
function TaskOperationSection({
  companyId,
  queryClient,
  selectedTaskId,
  setSelectedTaskId,
}: {
  companyId: string;
  queryClient: ReturnType<typeof useQueryClient>;
  selectedTaskId: string;
  setSelectedTaskId: (id: string) => void;
}) {
  // 完成确认的目标
  const [completeTarget, setCompleteTarget] = useState<Task | null>(null);
  // 重试子任务的弹窗
  const [retryTarget, setRetryTarget] = useState<Task | null>(null);
  // 校验计划结果
  const [validateResult, setValidateResult] = useState<ValidateResult | null>(null);
  const [validateTaskId, setValidateTaskId] = useState<string>('');

  const { data, isLoading, error, refetch } = useQuery<Task[]>({
    queryKey: ['tasks-advanced', companyId],
    queryFn: () => rpcCall<Task[]>('task.list', { company_id: companyId }),
    retry: 3,
    retryDelay: 1000,
  });

  const tasks = data ?? [];

  const completeMutation = useMutation({
    mutationFn: async (task: Task) =>
      rpcCall<{ task_id: string; version: number; status: string }>('task.complete', {
        task_id: task.task_id,
        expected_version: task.version,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks-advanced', companyId] });
      setCompleteTarget(null);
    },
  });

  const validateMutation = useMutation({
    mutationFn: async (taskId: string) =>
      rpcCall<ValidateResult>('workflow.plan.validate', {
        task_id: taskId,
        company_id: companyId,
      }),
    onSuccess: (res, taskId) => {
      setValidateResult(res);
      setValidateTaskId(taskId);
    },
  });

  if (isLoading) return <LoadingSpinner text="加载任务列表..." />;

  if (error) {
    return (
      <Section title="任务操作" icon={<CheckCircle2 size={16} />}>
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          重试
        </button>
      </Section>
    );
  }

  return (
    <Section title="任务操作" icon={<CheckCircle2 size={16} />}>
      {/* 检查点/节点选择用的任务下拉 */}
      <div className="mb-4">
        <label className="block text-sm text-gray-600 mb-1">选择任务（用于下方分区）</label>
        <select
          value={selectedTaskId}
          onChange={(e) => setSelectedTaskId(e.target.value)}
          className="w-full max-w-md px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
        >
          <option value="">请选择任务</option>
          {tasks.map((t) => (
            <option key={t.task_id} value={t.task_id}>
              {t.title}（{t.task_id}）
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500">
            <tr>
              <th className="text-left px-3 py-2 font-medium">标题</th>
              <th className="text-left px-3 py-2 font-medium">状态</th>
              <th className="text-left px-3 py-2 font-medium">版本</th>
              <th className="text-left px-3 py-2 font-medium">创建时间</th>
              <th className="text-left px-3 py-2 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-gray-400">
                  暂无任务
                </td>
              </tr>
            ) : (
              tasks.map((t) => (
                <tr key={t.task_id} className="border-t border-gray-100">
                  <td className="px-3 py-2 text-gray-800">{t.title}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="px-3 py-2 text-gray-600">{t.version}</td>
                  <td className="px-3 py-2 text-gray-500">{formatBJTime(t.created_at)}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setCompleteTarget(t)}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-green-600 text-white rounded-md hover:bg-green-700"
                      >
                        <CheckCircle2 size={12} />
                        完成
                      </button>
                      <button
                        onClick={() => setRetryTarget(t)}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-amber-600 text-white rounded-md hover:bg-amber-700"
                      >
                        <RefreshCw size={12} />
                        重试子任务
                      </button>
                      <button
                        onClick={() => validateMutation.mutate(t.task_id)}
                        disabled={validateMutation.isPending}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                      >
                        <ShieldCheck size={12} />
                        校验计划
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {validateResult && (
        <div className="mt-3 p-3 rounded-md border text-sm">
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-gray-700">
              校验结果（{validateTaskId}）：{validateResult.ok ? '通过' : '未通过'}
            </span>
            <button onClick={() => setValidateResult(null)} className="text-gray-400 hover:text-gray-600">
              <X size={14} />
            </button>
          </div>
          {!validateResult.ok && (
            <div className="text-red-600 text-xs space-y-1">
              {validateResult.rule && <p>规则: {validateResult.rule}</p>}
              {validateResult.error && <p>错误: {validateResult.error}</p>}
            </div>
          )}
        </div>
      )}

      {/* 完成确认 */}
      <ConfirmDialog
        open={!!completeTarget}
        title="确认完成"
        message={`确定要完成任务「${completeTarget?.title}」吗？`}
        confirmLabel="完成任务"
        danger={false}
        onConfirm={() => completeTarget && completeMutation.mutate(completeTarget)}
        onCancel={() => setCompleteTarget(null)}
      />

      {/* 重试子任务弹窗 */}
      {retryTarget && (
        <RetrySubtaskDialog
          task={retryTarget}
          onClose={() => setRetryTarget(null)}
        />
      )}
    </Section>
  );
}

function RetrySubtaskDialog({
  task,
  onClose,
}: {
  task: Task;
  onClose: () => void;
}) {
  const [nodes, setNodes] = useState<TaskNode[]>([]);
  const [nodesLoaded, setNodesLoaded] = useState(false);
  const [selectedNode, setSelectedNode] = useState('');
  const [reason, setReason] = useState('');
  const [loadError, setLoadError] = useState('');
  const [result, setResult] = useState<unknown>(null);

  const loadNodes = async () => {
    setLoadError('');
    try {
      const data = await rpcCall<TaskNode[]>('task.nodes', { task_id: task.task_id });
      setNodes(data ?? []);
      setNodesLoaded(true);
    } catch (e) {
      setLoadError(String(e instanceof Error ? e.message : e));
    }
  };

  const retryMutation = useMutation({
    mutationFn: async () =>
      rpcCall('task.retrySubtask', {
        task_id: task.task_id,
        node_id: selectedNode,
        reason: reason || undefined,
      }),
    onSuccess: (res) => {
      setResult(res);
    },
  });

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 w-[520px] shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-medium">重试子任务 - {task.title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {!nodesLoaded ? (
          <div>
            {loadError && <div className="text-red-500 text-sm mb-3">{loadError}</div>}
            <button
              onClick={loadNodes}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              加载节点列表
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">选择节点</label>
              <select
                value={selectedNode}
                onChange={(e) => setSelectedNode(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
              >
                <option value="">请选择节点</option>
                {nodes.map((n) => (
                  <option key={n.node_id} value={n.node_id}>
                    {n.node_id} · {n.node_type} · {n.status}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">原因（可选）</label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-20 resize-none"
                placeholder="请输入重试原因"
              />
            </div>
            <button
              onClick={() => retryMutation.mutate()}
              disabled={!selectedNode || retryMutation.isPending}
              className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-md hover:bg-amber-700 disabled:opacity-50"
            >
              {retryMutation.isPending ? '提交中...' : '提交重试'}
            </button>
            {retryMutation.error && (
              <div className="text-red-500 text-sm">{String(retryMutation.error.message)}</div>
            )}
            {result !== null && (
              <pre className="text-xs text-gray-600 bg-gray-50 rounded-md p-2 overflow-auto max-h-40">
                {JSON.stringify(result, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ===================== 2. 检查点分区 ===================== */
function CheckpointSection({
  companyId,
  selectedTaskId,
}: {
  companyId: string;
  selectedTaskId: string;
}) {
  const [checkpoints, setCheckpoints] = useState<CheckpointList | null>(null);
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadCheckpoints = async () => {
    if (!selectedTaskId) return;
    setLoadError('');
    setLoading(true);
    try {
      const data = await rpcCall<CheckpointList>('workflow.checkpoint.list', {
        task_id: selectedTaskId,
        company_id: companyId,
        page: { limit: 50, cursor: null },
      });
      setCheckpoints(data ?? []);
    } catch (e) {
      setLoadError(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Section title="检查点" icon={<ListChecks size={16} />}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm text-gray-600">
          当前选择任务: {selectedTaskId || '未选择'}
        </span>
        <button
          onClick={loadCheckpoints}
          disabled={!selectedTaskId || loading}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          <Inbox size={14} />
          {loading ? '查询中...' : '查检查点'}
        </button>
      </div>

      {loadError && <div className="text-red-500 text-sm mb-3">{loadError}</div>}

      {checkpoints === null ? (
        <div className="text-sm text-gray-400">尚未查询</div>
      ) : checkpoints.length === 0 ? (
        <div className="text-sm text-gray-400">暂无检查点</div>
      ) : (
        <div className="space-y-2">
          {checkpoints.map((cp, idx) => (
            <div
              key={idx}
              className="border border-gray-200 rounded-md p-3 text-xs bg-gray-50"
            >
              {cp && typeof cp === 'object' ? (
                Object.entries(cp as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} className="flex gap-2 py-0.5">
                    <span className="text-gray-500 w-32 shrink-0">{k}</span>
                    <span className="text-gray-800 break-all">
                      {typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-')}
                    </span>
                  </div>
                ))
              ) : (
                <span className="text-gray-800">{String(cp)}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

/* ===================== 3. 死信处理分区 ===================== */
function DeadLetterSection() {
  const [deadLetterId, setDeadLetterId] = useState('');
  const [resolution, setResolution] = useState<'resolved' | 'aborted'>('resolved');
  const [result, setResult] = useState<DeadLetterResolve | null>(null);
  const [err, setErr] = useState('');

  const resolveMutation = useMutation({
    mutationFn: async () =>
      rpcCall<DeadLetterResolve>('workflow.deadletter.resolve', {
        dead_letter_id: deadLetterId,
        resolution,
      }),
    onSuccess: (res) => {
      setResult(res);
      setErr('');
    },
    onError: (e) => {
      setErr(String(e instanceof Error ? e.message : e));
      setResult(null);
    },
  });

  return (
    <Section title="死信处理" icon={<Inbox size={16} />}>
      <div className="space-y-3 max-w-md">
        <div>
          <label className="block text-sm text-gray-600 mb-1">死信 ID</label>
          <input
            type="text"
            value={deadLetterId}
            onChange={(e) => setDeadLetterId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
            placeholder="请输入 dead_letter_id"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">处理方式</label>
          <select
            value={resolution}
            onChange={(e) => setResolution(e.target.value as 'resolved' | 'aborted')}
            className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
          >
            <option value="resolved">resolved - 已解决</option>
            <option value="aborted">aborted - 已终止</option>
          </select>
        </div>
        <button
          onClick={() => resolveMutation.mutate()}
          disabled={!deadLetterId || resolveMutation.isPending}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {resolveMutation.isPending ? '解决中...' : '解决死信'}
        </button>

        {err && <div className="text-red-500 text-sm">{err}</div>}
        {result && (
          <div className="p-3 rounded-md border border-gray-200 bg-gray-50 text-sm">
            <p className="text-gray-700">死信: {result.dead_letter_id}</p>
            <p className="text-gray-700">状态: {result.status}</p>
          </div>
        )}
      </div>
    </Section>
  );
}

/* ===================== 通用分区容器 ===================== */
function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border border-gray-200 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3 text-gray-700">
        {icon}
        <h3 className="text-sm font-medium">{title}</h3>
      </div>
      {children}
    </section>
  );
}
