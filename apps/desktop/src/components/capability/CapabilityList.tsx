import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, X, Check } from 'lucide-react';
import { rpcCall } from '../../services/rpcClient';
import { ConfirmDialog } from '../common/ConfirmDialog';
import type { Capability } from '../../types';

interface CapabilityListProps {
  companyId: string | null;
}

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

export function CapabilityList({ companyId }: CapabilityListProps) {
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Capability | null>(null);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formCategory, setFormCategory] = useState('custom');
  const [formVisibility, setFormVisibility] = useState('company');
  const [formCostPolicy, setFormCostPolicy] = useState(JSON.stringify({ default_model_tier: 'free', stability_level: 5 }, null, 2));
  const [formBindings, setFormBindings] = useState('[]');
  const [error, setError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Capability | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (companyId) params.company_id = companyId;
      const data = await rpcCall<Capability[]>('cap.capability.list', params);
      setCapabilities(data);
    } catch (e) {
      console.error('Failed to load capabilities:', e);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!formName.trim()) { setError('名称不能为空'); return; }
    setError('');
    try {
      const costPolicy = JSON.parse(formCostPolicy);
      const bindings = JSON.parse(formBindings);
      await rpcCall('cap.capability.create', {
        name: formName.trim(),
        description: formDesc,
        company_scope: companyId ? 'company' : 'global',
        company_id: companyId,
        source_category: formCategory,
        visibility: formVisibility,
        cost_policy: costPolicy,
        skill_bindings: bindings,
      });
      setShowCreate(false);
      resetForm();
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleUpdate = async () => {
    if (!editing || !formName.trim()) return;
    setError('');
    try {
      const costPolicy = JSON.parse(formCostPolicy);
      const bindings = JSON.parse(formBindings);
      await rpcCall('cap.capability.update', {
        capability_id: editing.capability_id,
        expected_version: editing.version,
        name: formName.trim(),
        description: formDesc,
        source_category: formCategory,
        visibility: formVisibility,
        cost_policy: costPolicy,
        skill_bindings: bindings,
      });
      setEditing(null);
      resetForm();
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await rpcCall('cap.capability.update', {
        capability_id: deleteTarget.capability_id,
        expected_version: deleteTarget.version,
        name: deleteTarget.name,
        description: deleteTarget.description || '',
        source_category: deleteTarget.source_category || 'custom',
        visibility: deleteTarget.visibility || 'company',
        cost_policy: deleteTarget.cost_policy,
        status: 'archived',
      });
      setDeleteTarget(null);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const resetForm = () => {
    setFormName('');
    setFormDesc('');
    setFormCategory('custom');
    setFormVisibility('company');
    setFormCostPolicy(JSON.stringify({ default_model_tier: 'free', stability_level: 5 }, null, 2));
    setFormBindings('[]');
    setError('');
  };

  const startEdit = async (cap: Capability) => {
    setEditing(cap);
    setFormName(cap.name);
    setFormDesc(cap.description || '');
    setFormCategory(cap.source_category || 'custom');
    setFormVisibility(cap.visibility || 'company');
    setFormCostPolicy(JSON.stringify(cap.cost_policy || { default_model_tier: 'free', stability_level: 5 }, null, 2));
    try {
      const detail = await rpcCall<Capability>('cap.capability.get', { capability_id: cap.capability_id });
      setFormBindings(JSON.stringify(detail.skill_bindings || [], null, 2));
    } catch {
      setFormBindings('[]');
    }
    setShowCreate(false);
    setError('');
  };

  if (loading) return <div className="p-6 text-gray-400 text-sm">加载中...</div>;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">能力管理</h2>
        <button
          onClick={() => { setShowCreate(true); setEditing(null); resetForm(); }}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600"
        >
          <Plus size={14} /> 新建能力
        </button>
      </div>

      {(showCreate || editing) && (
        <div className="mb-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-3">{editing ? '编辑能力' : '新建能力'}</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">名称 *</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="能力名称"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">描述</label>
              <input
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="能力描述"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">来源分类</label>
              <select
                value={formCategory}
                onChange={(e) => setFormCategory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
              >
                <option value="custom">自定义</option>
                <option value="standard">标准</option>
                <option value="artifact">产物</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">可见性</label>
              <select
                value={formVisibility}
                onChange={(e) => setFormVisibility(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
              >
                <option value="company">全公司</option>
                <option value="department">部门</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">成本策略 (JSON)</label>
              <textarea
                value={formCostPolicy}
                onChange={(e) => setFormCostPolicy(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 font-mono"
                rows={3}
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">技能绑定 (JSON)</label>
              <textarea
                value={formBindings}
                onChange={(e) => setFormBindings(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 font-mono"
                rows={3}
                placeholder='[{"skill_id":"...","skill_version":1}]'
              />
            </div>
          </div>
          {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
          <div className="flex gap-2 mt-3">
            <button
              onClick={editing ? handleUpdate : handleCreate}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600"
            >
              <Check size={14} /> {editing ? '保存' : '创建'}
            </button>
            <button
              onClick={() => { setShowCreate(false); setEditing(null); resetForm(); }}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-100 text-gray-600 rounded-md hover:bg-gray-200"
            >
              <X size={14} /> 取消
            </button>
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">名称</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">描述</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Scope</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">版本</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">状态</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {capabilities.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  暂无能力定义
                </td>
              </tr>
            ) : (
              capabilities.map((cap) => (
                <tr key={cap.capability_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-gray-800">{cap.name}</td>
                  <td className="px-4 py-2.5 text-gray-500 max-w-[200px] truncate">{cap.description || '-'}</td>
                  <td className="px-4 py-2.5 text-gray-500">{cap.company_scope === 'global' ? '全局' : '公司'}</td>
                  <td className="px-4 py-2.5 text-gray-500">v{cap.version}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 text-xs rounded-full ${STATUS_COLORS[cap.status] || 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[cap.status] || cap.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => startEdit(cap)} className="text-gray-400 hover:text-blue-500 p-1">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => setDeleteTarget(cap)} className="text-gray-400 hover:text-red-500 p-1">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认归档"
        message={`确定要归档能力「${deleteTarget?.name}」吗？`}
        confirmLabel="归档"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
