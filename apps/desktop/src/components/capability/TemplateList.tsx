import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, X, Check, Play, Archive } from 'lucide-react';
import { rpcCall } from '../../services/rpcClient';
import type { EmployeeTemplate } from '../../types';

interface TemplateListProps {
  companyId: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  active: '启用',
  archived: '已归档',
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  active: 'bg-green-100 text-green-700',
  archived: 'bg-red-100 text-red-600',
};

export function TemplateList({ companyId }: TemplateListProps) {
  const [templates, setTemplates] = useState<EmployeeTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<EmployeeTemplate | null>(null);
  const [formCapId, setFormCapId] = useState('');
  const [formCapVersion, setFormCapVersion] = useState('1');
  const [formRole, setFormRole] = useState('');
  const [formModel, setFormModel] = useState('gpt-4');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!companyId) { setLoading(false); return; }
    setLoading(true);
    try {
      const data = await rpcCall<EmployeeTemplate[]>('org.template.list', { company_id: companyId });
      setTemplates(data);
    } catch (e) {
      console.error('Failed to load templates:', e);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!companyId || !formCapId.trim() || !formRole.trim()) {
      setError('能力和角色名称不能为空');
      return;
    }
    setError('');
    try {
      await rpcCall('org.template.create', {
        company_id: companyId,
        capability_id: formCapId.trim(),
        capability_version: parseInt(formCapVersion) || 1,
        default_role: formRole.trim(),
        model: formModel,
      });
      setShowCreate(false);
      resetForm();
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleUpdate = async () => {
    if (!editing || !companyId) return;
    setError('');
    try {
      await rpcCall('org.template.update', {
        template_id: editing.template_id,
        company_id: companyId,
        expected_version: editing.version,
        capability_id: formCapId.trim() || undefined,
        capability_version: parseInt(formCapVersion) || undefined,
        default_role: formRole.trim() || undefined,
        model: formModel || undefined,
      });
      setEditing(null);
      resetForm();
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleActivate = async (t: EmployeeTemplate) => {
    if (!companyId) return;
    try {
      await rpcCall('org.template.activate', {
        template_id: t.template_id,
        company_id: companyId,
        expected_version: t.version,
      });
      load();
    } catch (e) {
      alert(String(e));
    }
  };

  const handleArchive = async (t: EmployeeTemplate) => {
    if (!companyId) return;
    try {
      await rpcCall('org.template.archive', {
        template_id: t.template_id,
        company_id: companyId,
        expected_version: t.version,
      });
      load();
    } catch (e) {
      alert(String(e));
    }
  };

  const resetForm = () => {
    setFormCapId('');
    setFormCapVersion('1');
    setFormRole('');
    setFormModel('gpt-4');
    setError('');
  };

  const startEdit = (t: EmployeeTemplate) => {
    setEditing(t);
    setFormCapId(t.capability_id);
    setFormCapVersion(String(t.capability_version));
    setFormRole(t.default_role);
    setFormModel(t.model);
    setShowCreate(false);
    setError('');
  };

  if (loading) return <div className="p-6 text-gray-400 text-sm">加载中...</div>;
  if (!companyId) return <div className="p-6 text-gray-400 text-sm">请先选择公司</div>;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">员工模板</h2>
        <button
          onClick={() => { setShowCreate(true); setEditing(null); resetForm(); }}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600"
        >
          <Plus size={14} /> 新建模板
        </button>
      </div>

      {(showCreate || editing) && (
        <div className="mb-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-3">{editing ? '编辑模板' : '新建模板'}</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Capability ID *</label>
              <input
                value={formCapId}
                onChange={(e) => setFormCapId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="关联的能力 ID"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">能力版本</label>
              <input
                value={formCapVersion}
                onChange={(e) => setFormCapVersion(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                type="number"
                min="1"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">默认角色 *</label>
              <input
                value={formRole}
                onChange={(e) => setFormRole(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="如：高级工程师"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">模型</label>
              <input
                value={formModel}
                onChange={(e) => setFormModel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                placeholder="gpt-4"
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
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">角色</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">模型</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">能力版本</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">状态</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {templates.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  暂无模板
                </td>
              </tr>
            ) : (
              templates.map((t) => (
                <tr key={t.template_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-gray-800">{t.default_role}</td>
                  <td className="px-4 py-2.5 text-gray-500">{t.model}</td>
                  <td className="px-4 py-2.5 text-gray-500">v{t.capability_version}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 text-xs rounded-full ${STATUS_COLORS[t.status] || 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[t.status] || t.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {t.status === 'draft' && (
                        <>
                          <button onClick={() => startEdit(t)} className="text-gray-400 hover:text-blue-500 p-1" title="编辑">
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => handleActivate(t)} className="text-gray-400 hover:text-green-500 p-1" title="激活">
                            <Play size={14} />
                          </button>
                        </>
                      )}
                      {t.status === 'active' && (
                        <button onClick={() => handleArchive(t)} className="text-gray-400 hover:text-red-500 p-1" title="归档">
                          <Archive size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
