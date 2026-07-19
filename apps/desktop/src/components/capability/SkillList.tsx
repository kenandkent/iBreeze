import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, X, Check } from 'lucide-react';
import { rpcCall } from '../../services/rpcClient';
import { ConfirmDialog } from '../common/ConfirmDialog';
import type { Skill } from '../../types';

interface SkillListProps {
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

export function SkillList({ companyId }: SkillListProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [formName, setFormName] = useState('');
  const [formPromptId, setFormPromptId] = useState('');
  const [formBindings, setFormBindings] = useState('');
  const [error, setError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (companyId) params.company_id = companyId;
      const data = await rpcCall<Skill[]>('cap.skill.list', params);
      setSkills(data);
    } catch (e) {
      console.error('Failed to load skills:', e);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const handleCreate = async () => {
    if (!formName.trim()) {
      setError('名称不能为空');
      return;
    }
    setError('');
    try {
      await rpcCall('cap.skill.create', {
        name: formName.trim(),
        company_scope: companyId ? 'company' : 'global',
        company_id: companyId,
        prompt_asset_id: formPromptId || '',
        tool_bindings: formBindings ? JSON.parse(formBindings) : [],
      });
      setShowCreate(false);
      resetForm();
      loadSkills();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleUpdate = async () => {
    if (!editingSkill || !formName.trim()) return;
    setError('');
    try {
      await rpcCall('cap.skill.update', {
        skill_id: editingSkill.skill_id,
        expected_version: editingSkill.version,
        name: formName.trim(),
        prompt_asset_id: formPromptId || editingSkill.prompt_asset_id,
      });
      setEditingSkill(null);
      resetForm();
      loadSkills();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await rpcCall('cap.skill.update', {
        skill_id: deleteTarget.skill_id,
        expected_version: deleteTarget.version,
        name: deleteTarget.name,
        status: 'archived',
      });
      setDeleteTarget(null);
      loadSkills();
    } catch (e) {
      setError(String(e));
    }
  };

  const resetForm = () => {
    setFormName('');
    setFormPromptId('');
    setFormBindings('');
    setError('');
  };

  const startEdit = (skill: Skill) => {
    setEditingSkill(skill);
    setFormName(skill.name);
    setFormPromptId(skill.prompt_asset_id || '');
    setFormBindings(skill.tool_bindings ? JSON.stringify(skill.tool_bindings, null, 2) : '');
    setShowCreate(false);
    setError('');
  };

  if (loading) {
    return <div className="p-6 text-gray-400 text-sm">加载中...</div>;
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">技能管理</h2>
        <button
          onClick={() => { setShowCreate(true); setEditingSkill(null); resetForm(); }}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600"
        >
          <Plus size={14} /> 新建技能
        </button>
      </div>

      {(showCreate || editingSkill) && (
        <div className="mb-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            {editingSkill ? '编辑技能' : '新建技能'}
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">名称 *</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="技能名称"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Prompt Asset ID</label>
              <input
                value={formPromptId}
                onChange={(e) => setFormPromptId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="关联的 Prompt Asset"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">工具绑定 (JSON)</label>
              <textarea
                value={formBindings}
                onChange={(e) => setFormBindings(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                rows={3}
                placeholder='[{"tool_name": "search", "entrypoint": "search.py"}]'
              />
            </div>
          </div>
          {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
          <div className="flex gap-2 mt-3">
            <button
              onClick={editingSkill ? handleUpdate : handleCreate}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600"
            >
              <Check size={14} /> {editingSkill ? '保存' : '创建'}
            </button>
            <button
              onClick={() => { setShowCreate(false); setEditingSkill(null); resetForm(); }}
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
            {skills.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  暂无技能，点击右上角创建
                </td>
              </tr>
            ) : (
              skills.map((skill) => (
                <tr key={skill.skill_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-gray-800">{skill.name}</td>
                  <td className="px-4 py-2.5 text-gray-500">{skill.company_scope === 'global' ? '全局' : '公司'}</td>
                  <td className="px-4 py-2.5 text-gray-500">v{skill.version}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 text-xs rounded-full ${STATUS_COLORS[skill.status] || 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[skill.status] || skill.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => startEdit(skill)}
                        className="text-gray-400 hover:text-blue-500 p-1"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(skill)}
                        className="text-gray-400 hover:text-red-500 p-1"
                      >
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
        title="确认删除"
        message={`确定要归档技能「${deleteTarget?.name}」吗？`}
        confirmLabel="归档"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
