import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, X, Check } from 'lucide-react';
import { rpcCall } from '../../services/rpcClient';
import { ConfirmDialog } from '../common/ConfirmDialog';
import type { PromptAsset } from '../../types';

interface PromptListProps {
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

const DEFAULT_SEGMENTS = {
  system: '',
  developer: '',
  user_template: '',
  tool_instructions: '',
  output_contract: '',
};

export function PromptList({ companyId }: PromptListProps) {
  const [prompts, setPrompts] = useState<PromptAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<PromptAsset | null>(null);
  const [formName, setFormName] = useState('');
  const [formSegments, setFormSegments] = useState(JSON.stringify(DEFAULT_SEGMENTS, null, 2));
  const [formVariables, setFormVariables] = useState('[]');
  const [formSlots, setFormSlots] = useState('conversation,knowledge');
  const [error, setError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<PromptAsset | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (companyId) params.company_id = companyId;
      const data = await rpcCall<PromptAsset[]>('cap.prompt.list', params);
      setPrompts(data);
    } catch (e) {
      console.error('Failed to load prompts:', e);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!formName.trim()) { setError('名称不能为空'); return; }
    setError('');
    try {
      const segments = JSON.parse(formSegments);
      const variables = JSON.parse(formVariables);
      const contextSlots = formSlots.split(',').map(s => s.trim()).filter(Boolean);
      await rpcCall('cap.prompt.create', {
        name: formName.trim(),
        company_scope: companyId ? 'company' : 'global',
        company_id: companyId,
        segments,
        variables,
        context_slots: contextSlots,
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
      const segments = JSON.parse(formSegments);
      const variables = JSON.parse(formVariables);
      const contextSlots = formSlots.split(',').map(s => s.trim()).filter(Boolean);
      await rpcCall('cap.prompt.update', {
        prompt_id: editing.prompt_asset_id,
        expected_version: editing.version,
        name: formName.trim(),
        segments,
        variables,
        context_slots: contextSlots,
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
      await rpcCall('cap.prompt.update', {
        prompt_id: deleteTarget.prompt_asset_id,
        expected_version: deleteTarget.version,
        name: deleteTarget.name,
        segments: deleteTarget.segments,
        variables: deleteTarget.variables,
        context_slots: deleteTarget.context_slots,
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
    setFormSegments(JSON.stringify(DEFAULT_SEGMENTS, null, 2));
    setFormVariables('[]');
    setFormSlots('conversation,knowledge');
    setError('');
  };

  const startEdit = (p: PromptAsset) => {
    setEditing(p);
    setFormName(p.name);
    setFormSegments(JSON.stringify(p.segments || DEFAULT_SEGMENTS, null, 2));
    setFormVariables(JSON.stringify(p.variables || [], null, 2));
    setFormSlots((p.context_slots || []).join(','));
    setShowCreate(false);
    setError('');
  };

  if (loading) return <div className="p-6 text-gray-400 text-sm">加载中...</div>;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Prompt 资产</h2>
        <button
          onClick={() => { setShowCreate(true); setEditing(null); resetForm(); }}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600"
        >
          <Plus size={14} /> 新建
        </button>
      </div>

      {(showCreate || editing) && (
        <div className="mb-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-3">{editing ? '编辑 Prompt' : '新建 Prompt'}</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">名称 *</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="Prompt 名称"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">上下文槽位</label>
              <input
                value={formSlots}
                onChange={(e) => setFormSlots(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="conversation,knowledge,memory"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Segments (JSON)</label>
              <textarea
                value={formSegments}
                onChange={(e) => setFormSegments(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 font-mono"
                rows={6}
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Variables (JSON)</label>
              <textarea
                value={formVariables}
                onChange={(e) => setFormVariables(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 font-mono"
                rows={3}
                placeholder='[{"name":"task_name","type":"string","required":true}]'
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
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Scope</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">版本</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">状态</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {prompts.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  暂无 Prompt 资产
                </td>
              </tr>
            ) : (
              prompts.map((p) => (
                <tr key={p.prompt_asset_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-gray-800">{p.name}</td>
                  <td className="px-4 py-2.5 text-gray-500">{p.company_scope === 'global' ? '全局' : '公司'}</td>
                  <td className="px-4 py-2.5 text-gray-500">v{p.version}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 text-xs rounded-full ${STATUS_COLORS[p.status] || 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[p.status] || p.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => startEdit(p)} className="text-gray-400 hover:text-blue-500 p-1">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => setDeleteTarget(p)} className="text-gray-400 hover:text-red-500 p-1">
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
        message={`确定要归档 Prompt「${deleteTarget?.name}」吗？`}
        confirmLabel="归档"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
