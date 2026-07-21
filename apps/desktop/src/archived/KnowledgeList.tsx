import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ConfirmDialog } from '../common/ConfirmDialog';
import type { KnowledgeDocument } from '../../types';
import { BookOpen, X, Pencil, Trash2 } from 'lucide-react';

export function KnowledgeList() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<KnowledgeDocument | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDocument | null>(null);
  const [form, setForm] = useState({ title: '', content: '', source_category: 'custom', company_id: '' });

  const { data, isLoading, error, refetch } = useQuery<KnowledgeDocument[]>({
    queryKey: ['knowledge'],
    queryFn: () => rpcCall<KnowledgeDocument[]>('knowledge.list'),
    retry: 3,
    retryDelay: 1000,
  });

  const createMutation = useMutation({
    mutationFn: async (data: typeof form) => rpcCall('knowledge.create', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
      setShowCreate(false);
      setForm({ title: '', content: '', source_category: 'custom', company_id: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (doc: KnowledgeDocument) => rpcCall('knowledge.update', {
      document_id: doc.document_id,
      company_id: doc.company_id,
      expected_version: 1,
      title: doc.title,
      content: '',
      source_category: doc.source_category,
      status: 'archived',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
      setDeleteTarget(null);
    },
  });

  const handleEdit = async () => {
    if (!editing || !form.title) return;
    try {
      await rpcCall('knowledge.update', {
        document_id: editing.document_id,
        company_id: editing.company_id,
        expected_version: 1,
        title: form.title,
        content: form.content,
        source_category: form.source_category,
      });
      setEditing(null);
      setForm({ title: '', content: '', source_category: 'custom', company_id: '' });
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    } catch (e) {
      console.error('Failed to update knowledge:', e);
    }
  };

  const startEdit = (doc: KnowledgeDocument) => {
    setEditing(doc);
    setForm({
      title: doc.title,
      content: '',
      source_category: doc.source_category,
      company_id: doc.company_id,
    });
    setShowCreate(false);
  };

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          重试
        </button>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium text-gray-700">知识库</h2>
        <button
          onClick={() => { setShowCreate(true); setEditing(null); setForm({ title: '', content: '', source_category: 'custom', company_id: '' }); }}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          添加文档
        </button>
      </div>

      {(showCreate || editing) && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[480px] shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">{editing ? '编辑文档' : '添加文档'}</h3>
              <button onClick={() => { setShowCreate(false); setEditing(null); }} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              {!editing && (
                <div>
                  <label className="block text-sm text-gray-600 mb-1">公司 ID</label>
                  <input
                    type="text"
                    value={form.company_id}
                    onChange={(e) => setForm({ ...form, company_id: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                    placeholder="请输入公司 ID"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm text-gray-600 mb-1">标题</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                  placeholder="请输入文档标题"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">分类</label>
                <select
                  value={form.source_category}
                  onChange={(e) => setForm({ ...form, source_category: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                >
                  <option value="custom">自定义</option>
                  <option value="policy">政策文档</option>
                  <option value="technical">技术文档</option>
                  <option value="training">培训资料</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">内容</label>
                <textarea
                  value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-28 resize-none"
                  placeholder="请输入文档内容"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => { setShowCreate(false); setEditing(null); }}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800"
              >
                取消
              </button>
              <button
                onClick={editing ? handleEdit : () => createMutation.mutate(form)}
                disabled={!form.title || createMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {editing ? '保存' : createMutation.isPending ? '添加中...' : '确认添加'}
              </button>
            </div>
          </div>
        </div>
      )}

      {(!data || data.length === 0) ? (
        <div className="text-center py-12 text-gray-400">
          <BookOpen className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无文档</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">标题</th>
                <th className="px-4 py-2 font-medium">来源分类</th>
                <th className="px-4 py-2 font-medium">状态</th>
                <th className="px-4 py-2 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((doc) => (
                <tr key={doc.document_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-gray-800">{doc.title}</td>
                  <td className="px-4 py-2.5 text-gray-600">{doc.source_category}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={doc.status} /></td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => startEdit(doc)} className="text-gray-400 hover:text-blue-500 p-1">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => setDeleteTarget(doc)} className="text-gray-400 hover:text-red-500 p-1">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除"
        message={`确定要删除文档「${deleteTarget?.title}」吗？`}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
