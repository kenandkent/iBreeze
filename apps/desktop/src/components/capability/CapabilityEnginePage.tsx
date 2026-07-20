import { useState, useEffect, useCallback } from 'react';
import { Cpu, Camera, BarChart3, Plus, GitBranch, Send } from 'lucide-react';
import { rpcCall } from '../../services/rpcClient';
import { useAppStore } from '../../stores/appStore';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { LoadingSpinner } from '../common/LoadingSpinner';
import type { Capability, Employee } from '../../types';

// 能力状态展示映射
const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  review: '评审中',
  published: '已发布',
  deprecated: '已弃用',
  archived: '已归档',
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  review: 'bg-yellow-100 text-yellow-700',
  published: 'bg-green-100 text-green-700',
  deprecated: 'bg-orange-100 text-orange-700',
  archived: 'bg-red-100 text-red-600',
};

// 容错渲染任意返回对象
function JsonCard({ title, data }: { title: string; data: unknown }) {
  const obj = (data ?? {}) as Record<string, unknown>;
  const entries = Object.entries(obj);
  return (
    <div className="mt-3 p-4 bg-white border border-gray-200 rounded-lg">
      <h4 className="text-sm font-medium text-gray-700 mb-3">{title}</h4>
      {entries.length === 0 ? (
        <p className="text-xs text-gray-400">（无返回数据）</p>
      ) : (
        <div className="space-y-2">
          {entries.map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs">
              <span className="shrink-0 w-40 text-gray-500 font-mono break-all">{k}</span>
              <span className="text-gray-800 break-all">
                {typeof v === 'object' && v !== null
                  ? <pre className="whitespace-pre-wrap font-mono text-[11px] text-gray-700">{JSON.stringify(v, null, 2)}</pre>
                  : String(v)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CapabilityEnginePage() {
  const currentCompanyId = useAppStore((s) => s.currentCompanyId);

  if (!currentCompanyId) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center py-20 text-gray-400 text-sm">
          请先在左侧选择一家公司
        </div>
      </div>
    );
  }

  return <Inner companyId={currentCompanyId} />;
}

function Inner({ companyId }: { companyId: string }) {
  const loadCaps = useCallback(async () => {
    const params: Record<string, unknown> = { company_id: companyId };
    return rpcCall<Capability[]>('cap.capability.list', params);
  }, [companyId]);

  const [caps, setCaps] = useState<Capability[]>([]);
  const [loadingCaps, setLoadingCaps] = useState(true);

  // 状态机确认弹窗
  const [confirm, setConfirm] = useState<{ cap: Capability; action: string } | null>(null);

  // 选中能力（用于快照/指标/engine）
  const [selectedCapId, setSelectedCapId] = useState<string>('');

  // 引擎装配
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [empId, setEmpId] = useState('');
  const [resolveResult, setResolveResult] = useState<unknown>(null);
  const [resolveLoading, setResolveLoading] = useState(false);

  // 快照 / 指标
  const [snapshot, setSnapshot] = useState<unknown>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [metrics, setMetrics] = useState<unknown>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);

  // 版本列表
  const [versions, setVersions] = useState<unknown[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [versionLoading, setVersionLoading] = useState(false);

  // 新建版本
  const [showCreateVer, setShowCreateVer] = useState(false);

  const refresh = useCallback(async () => {
    setLoadingCaps(true);
    try {
      const data = await loadCaps();
      setCaps(data);
      if (!selectedCapId && data.length > 0) setSelectedCapId(data[0].capability_id);
    } catch (e) {
      console.error('load caps failed', e);
    } finally {
      setLoadingCaps(false);
    }
  }, [loadCaps, selectedCapId]);

  useEffect(() => {
    refresh();
    (async () => {
      try {
        const emps = await rpcCall<Employee[]>('org.employee.list', { company_id: companyId });
        setEmployees(emps);
        if (emps.length > 0) setEmpId(emps[0].employee_id);
      } catch (e) {
        console.error('load employees failed', e);
      }
    })();
  }, [refresh, companyId]);

  // 状态机操作
  const runAction = async () => {
    if (!confirm) return;
    const { cap, action } = confirm;
    try {
      const methodMap: Record<string, string> = {
        submitReview: 'cap.capability.submitReview',
        publish: 'cap.capability.publish',
        deprecate: 'cap.capability.deprecate',
        archive: 'cap.capability.archive',
      };
      await rpcCall(methodMap[action], {
        capability_id: cap.capability_id,
        expected_version: cap.version,
      });
      setConfirm(null);
      await refresh();
    } catch (e) {
      console.error(`${action} failed`, e);
    }
  };

  // 引擎解析
  const handleResolve = async () => {
    if (!empId || !selectedCapId) return;
    setResolveLoading(true);
    setResolveResult(null);
    try {
      const cap = caps.find((c) => c.capability_id === selectedCapId);
      const result = await rpcCall<unknown>('cap.engine.resolve', {
        employee: { employee_id: empId },
        capability_snapshot: cap ? { capability_id: cap.capability_id, name: cap.name } : {},
      });
      setResolveResult(result);
    } catch (e) {
      setResolveResult({ error: String(e) });
    } finally {
      setResolveLoading(false);
    }
  };

  const handleSnapshot = async () => {
    if (!selectedCapId) return;
    setSnapshotLoading(true);
    setSnapshot(null);
    try {
      const result = await rpcCall<unknown>('cap.snapshot.build', { capability_id: selectedCapId });
      setSnapshot(result);
    } catch (e) {
      setSnapshot({ error: String(e) });
    } finally {
      setSnapshotLoading(false);
    }
  };

  const handleMetrics = async () => {
    if (!selectedCapId) return;
    setMetricsLoading(true);
    setMetrics(null);
    try {
      const result = await rpcCall<unknown>('cap.metrics.get', { capability_id: selectedCapId });
      setMetrics(result);
    } catch (e) {
      setMetrics({ error: String(e) });
    } finally {
      setMetricsLoading(false);
    }
  };

  const handleShowVersions = async () => {
    if (!selectedCapId) return;
    setVersionLoading(true);
    setShowVersions(true);
    try {
      const result = await rpcCall<unknown[]>('cap.capability.version.list', { capability_id: selectedCapId });
      setVersions(result);
    } catch (e) {
      setVersions([{ error: String(e) }]);
    } finally {
      setVersionLoading(false);
    }
  };

  const handleCreateVersion = async () => {
    if (!selectedCapId) return;
    try {
      await rpcCall('cap.capability.createVersion', { capability_id: selectedCapId });
      await refresh();
      setShowCreateVer(false);
    } catch (e) {
      console.error('createVersion failed', e);
    }
  };

  const confirmMeta: Record<string, { title: string; message: string; label: string }> = {
    submitReview: { title: '提交评审', message: '提交评审后将进入评审中状态，确认？', label: '提交评审' },
    publish: { title: '发布能力', message: '确认发布该能力？', label: '发布' },
    deprecate: { title: '弃用能力', message: '确认弃用该能力？', label: '弃用' },
    archive: { title: '归档能力', message: '确认归档该能力？', label: '归档' },
  };

  if (loadingCaps) return <LoadingSpinner text="加载能力列表..." />;

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-lg font-semibold text-gray-800">能力引擎与状态机</h2>

      {/* 分区一：能力列表 + 状态机 */}
      <section className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <header className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-700">能力列表与状态机</h3>
          <select
            value={selectedCapId}
            onChange={(e) => setSelectedCapId(e.target.value)}
            className="px-2 py-1 text-sm border border-gray-200 rounded-md focus:outline-none focus:border-blue-400"
          >
            <option value="">选择能力...</option>
            {caps.map((c) => (
              <option key={c.capability_id} value={c.capability_id}>{c.name}</option>
            ))}
          </select>
        </header>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">名称</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">版本</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">状态</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {caps.length === 0 ? (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400">暂无能力定义</td></tr>
            ) : (
              caps.map((cap) => (
                <tr key={cap.capability_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-gray-800">{cap.name}</td>
                  <td className="px-4 py-2.5 text-gray-500">v{cap.version}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 text-xs rounded-full ${STATUS_COLORS[cap.status] || 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[cap.status] || cap.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setConfirm({ cap, action: 'submitReview' })}
                        className="px-2 py-1 text-xs rounded-md bg-blue-50 text-blue-600 hover:bg-blue-100">评审</button>
                      <button onClick={() => setConfirm({ cap, action: 'publish' })}
                        className="px-2 py-1 text-xs rounded-md bg-green-50 text-green-600 hover:bg-green-100">发布</button>
                      <button onClick={() => setConfirm({ cap, action: 'deprecate' })}
                        className="px-2 py-1 text-xs rounded-md bg-orange-50 text-orange-600 hover:bg-orange-100">弃用</button>
                      <button onClick={() => setConfirm({ cap, action: 'archive' })}
                        className="px-2 py-1 text-xs rounded-md bg-red-50 text-red-600 hover:bg-red-100">归档</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div className="flex items-center gap-2 px-4 py-3 border-t border-gray-100">
          <button onClick={() => setShowCreateVer(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600">
            <Plus size={14} /> 新建版本
          </button>
          <button onClick={handleShowVersions}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-100 text-gray-600 rounded-md hover:bg-gray-200">
            <GitBranch size={14} /> 版本列表
          </button>
        </div>
      </section>

      {/* 分区二：引擎装配 */}
      <section className="bg-white border border-gray-200 rounded-lg p-4">
        <header className="flex items-center gap-2 mb-3">
          <Cpu size={16} className="text-blue-500" />
          <h3 className="text-sm font-medium text-gray-700">引擎装配 (cap.engine.resolve)</h3>
        </header>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">员工</label>
            <select value={empId} onChange={(e) => setEmpId(e.target.value)}
              className="px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:border-blue-400">
              <option value="">选择员工...</option>
              {employees.map((e) => (
                <option key={e.employee_id} value={e.employee_id}>{e.name}（{e.role_name}）</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">能力</label>
            <select value={selectedCapId} onChange={(e) => setSelectedCapId(e.target.value)}
              className="px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:border-blue-400">
              <option value="">选择能力...</option>
              {caps.map((c) => (
                <option key={c.capability_id} value={c.capability_id}>{c.name}</option>
              ))}
            </select>
          </div>
          <button onClick={handleResolve} disabled={resolveLoading || !empId || !selectedCapId}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-40">
            <Send size={14} /> {resolveLoading ? '解析中...' : '解析'}
          </button>
        </div>
        {resolveResult != null && <JsonCard title="运行时配置" data={resolveResult} />}
      </section>

      {/* 分区三：快照与指标 */}
      <section className="bg-white border border-gray-200 rounded-lg p-4">
        <header className="flex items-center gap-2 mb-3">
          <Camera size={16} className="text-purple-500" />
          <h3 className="text-sm font-medium text-gray-700">快照与指标</h3>
        </header>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-gray-500">当前能力：</span>
          <span className="text-xs text-gray-800">
            {caps.find((c) => c.capability_id === selectedCapId)?.name || '未选择'}
          </span>
        </div>
        <div className="flex gap-2">
          <button onClick={handleSnapshot} disabled={snapshotLoading || !selectedCapId}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-purple-500 text-white rounded-md hover:bg-purple-600 disabled:opacity-40">
            <Camera size={14} /> {snapshotLoading ? '构建中...' : '构建快照'}
          </button>
          <button onClick={handleMetrics} disabled={metricsLoading || !selectedCapId}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-40">
            <BarChart3 size={14} /> {metricsLoading ? '查询中...' : '查看指标'}
          </button>
        </div>
        {snapshot != null && <JsonCard title="质量快照 (cap.snapshot.build)" data={snapshot} />}
        {metrics != null && <JsonCard title="指标 (cap.metrics.get)" data={metrics} />}
      </section>

      {/* 新建版本弹窗 */}
      <ConfirmDialog open={showCreateVer}
        title="新建版本" message="确认基于当前能力创建新版本？" confirmLabel="创建"
        onConfirm={handleCreateVersion} onCancel={() => setShowCreateVer(false)} danger={false} />

      {/* 版本列表弹窗 */}
      <ConfirmDialog open={showVersions}
        title="版本列表" message=""
        confirmLabel="关闭" onConfirm={() => setShowVersions(false)} onCancel={() => setShowVersions(false)} danger={false} />

      {showVersions && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowVersions(false)}>
          <div className="bg-white rounded-lg p-6 w-[480px] max-h-[70vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-medium text-gray-800 mb-3">版本列表</h3>
            {versionLoading ? <LoadingSpinner text="加载版本..." /> : (
              versions.length === 0 ? <p className="text-sm text-gray-400">暂无版本</p> : (
                <div className="space-y-2">
                  {versions.map((v, i) => (
                    <div key={i} className="text-xs"><JsonCard title={`版本 ${i + 1}`} data={v} /></div>
                  ))}
                </div>
              )
            )}
            <div className="flex justify-end mt-4">
              <button onClick={() => setShowVersions(false)}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-md">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 状态机确认弹窗 */}
      <ConfirmDialog
        open={!!confirm}
        title={confirm ? confirmMeta[confirm.action].title : ''}
        message={confirm ? confirmMeta[confirm.action].message : ''}
        confirmLabel={confirm ? confirmMeta[confirm.action].label : '确认'}
        onConfirm={runAction}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}
