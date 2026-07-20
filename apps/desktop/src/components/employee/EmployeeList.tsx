import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ConfirmDialog } from '../common/ConfirmDialog';
import type { Employee, Company, Department, EmployeeTemplate } from '../../types';
import { Users, X, Pencil, Trash2, UserCog, Play, Pause, RotateCcw, Archive } from 'lucide-react';

const emptyForm = { name: '', role_name: '', company_id: '', department_id: '', template_id: '' };

// 员工状态机：根据当前状态决定可用转换
const STATUS_ACTIONS: Record<string, { key: string; label: string; rpc: string; icon: typeof Play; danger?: boolean }[]> = {
  active: [
    { key: 'suspend', label: '暂停', rpc: 'org.employee.suspend', icon: Pause },
    { key: 'archive', label: '归档', rpc: 'org.employee.archive', icon: Archive, danger: true },
  ],
  suspended: [
    { key: 'resume', label: '恢复', rpc: 'org.employee.resume', icon: RotateCcw },
    { key: 'archive', label: '归档', rpc: 'org.employee.archive', icon: Archive, danger: true },
  ],
  archived: [
    { key: 'activate', label: '激活', rpc: 'org.employee.activate', icon: Play },
  ],
  inactive: [
    { key: 'activate', label: '激活', rpc: 'org.employee.activate', icon: Play },
  ],
};

export function EmployeeList() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [confirmDelete, setConfirmDelete] = useState<Employee | null>(null);
  const [statusTarget, setStatusTarget] = useState<Employee | null>(null);
  const [statusAction, setStatusAction] = useState<{ key: string; label: string; rpc: string; danger?: boolean } | null>(null);
  const [managerTarget, setManagerTarget] = useState<Employee | null>(null);
  const [managerId, setManagerId] = useState('');

  const { data, isLoading, error, refetch } = useQuery<Employee[]>({
    queryKey: ['employees'],
    queryFn: () => rpcCall<Employee[]>('org.employee.list'),
    retry: 3,
    retryDelay: 1000,
  });

  const { data: companies } = useQuery<Company[]>({
    queryKey: ['companies'],
    queryFn: () => rpcCall<Company[]>('org.company.list'),
  });

  const activeCompanies = companies?.filter((c) => c.status === 'active');

  const { data: departments } = useQuery<Department[]>({
    queryKey: ['departments', form.company_id],
    queryFn: () => rpcCall<Department[]>('org.department.list', { company_id: form.company_id }),
    enabled: !!form.company_id,
  });

  const { data: templates } = useQuery<EmployeeTemplate[]>({
    queryKey: ['employeeTemplates', activeCompanies?.map((c) => c.company_id).join(',')],
    queryFn: async () => {
      const comps = activeCompanies ?? [];
      const lists = await Promise.all(
        comps.map((c) => rpcCall<EmployeeTemplate[]>('org.template.list', { company_id: c.company_id, status: 'active' }).catch(() => [] as EmployeeTemplate[]))
      );
      return lists.flat();
    },
    enabled: !!activeCompanies && activeCompanies.length > 0,
  });

  const templateMap = new Map((templates ?? []).map((t) => [t.template_id, t]));

  const createMutation = useMutation({
    mutationFn: (data: typeof form) => rpcCall('org.employee.create', {
      name: data.name,
      role_name: data.role_name,
      company_id: data.company_id,
      department_id: data.department_id,
      template_id: data.template_id,
      employee_type: 'ai_agent',
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['employees'] }); closeModal(); },
  });

  const updateMutation = useMutation({
    mutationFn: (data: typeof form & { employee_id: string }) => rpcCall('org.employee.update', data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['employees'] }); closeModal(); },
  });

  const deleteMutation = useMutation({
    mutationFn: (employee_id: string) => {
      console.log('[iBreeze] deleteEmployee called', { employee_id });
      return rpcCall('org.employee.delete', { employee_id });
    },
    onSuccess: (result) => { console.log('[iBreeze] deleteEmployee success', result); queryClient.invalidateQueries({ queryKey: ['employees'] }); },
    onError: (err: Error) => { console.error('[iBreeze] deleteEmployee error:', err); alert('删除员工失败: ' + err.message); },
  });

  // 员工状态机：激活/暂停/恢复/归档
  const statusMutation = useMutation({
    mutationFn: ({ emp, rpc }: { emp: Employee; rpc: string }) => rpcCall(rpc, { employee_id: emp.employee_id }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['employees'] }); setStatusTarget(null); setStatusAction(null); },
    onError: (err: Error) => alert('操作失败: ' + err.message),
  });

  // 设置上级（制造汇报链）
  const setManagerMutation = useMutation({
    mutationFn: ({ emp, manager_employee_id }: { emp: Employee; manager_employee_id: string }) =>
      rpcCall('org.employee.setManager', { employee_id: emp.employee_id, manager_employee_id }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['employees'] }); setManagerTarget(null); setManagerId(''); },
    onError: (err: Error) => alert('设置上级失败: ' + err.message),
  });

  // 设上级弹窗所需的同公司员工下拉
  const { data: peers } = useQuery<Employee[]>({
    queryKey: ['employees', managerTarget?.company_id],
    queryFn: () => rpcCall<Employee[]>('org.employee.list'),
    enabled: !!managerTarget,
  });
  const peerOptions = (peers ?? []).filter((p) => p.employee_id !== managerTarget?.employee_id && p.company_id === managerTarget?.company_id);

  function closeModal() { setShowModal(false); setEditEmployee(null); setForm(emptyForm); }

  function openEdit(emp: Employee) {
    setForm({ name: emp.name, role_name: emp.role_name, company_id: emp.company_id, department_id: emp.department_id || '', template_id: emp.template_id || '' });
    setEditEmployee(emp);
    setShowModal(true);
  }

  function handleSubmit() {
    if (editEmployee) {
      updateMutation.mutate({ ...form, employee_id: editEmployee.employee_id });
    } else {
      createMutation.mutate(form);
    }
  }

  if (isLoading) return <LoadingSpinner />;
  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium text-gray-700">员工列表</h2>
        <button onClick={() => { setForm(emptyForm); setEditEmployee(null); setShowModal(true); }}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors">
          新建员工
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">{editEmployee ? '编辑员工' : '新建员工'}</h3>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">所属公司</label>
                <select value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value, department_id: '' })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]">
                  <option value="">请选择公司</option>
                  {activeCompanies?.map((c) => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">所属部门</label>
                <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]" disabled={!form.company_id}>
                  <option value="">请选择部门</option>
                  {departments?.map((d) => <option key={d.department_id} value={d.department_id}>{d.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">基座模板</label>
                <select value={form.template_id} onChange={(e) => setForm({ ...form, template_id: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]" disabled={!form.company_id}>
                  <option value="">不绑定模板</option>
                  {(templates ?? [])
                    .filter((t) => !form.company_id || t.company_id === form.company_id)
                    .map((t) => <option key={t.template_id} value={t.template_id}>{t.default_role} · {t.model} · {t.provider_id || 'openai'}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">姓名</label>
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" placeholder="请输入姓名" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">角色</label>
                <input type="text" value={form.role_name} onChange={(e) => setForm({ ...form, role_name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" placeholder="如：开发工程师、项目经理" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={closeModal} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button onClick={handleSubmit} disabled={!form.name || !form.company_id || createMutation.isPending || updateMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                {createMutation.isPending || updateMutation.isPending ? '处理中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title="删除确认"
        message={confirmDelete ? `确定删除员工「${confirmDelete.name}」？` : ''}
        confirmLabel="删除"
        onConfirm={() => { if (confirmDelete) deleteMutation.mutate(confirmDelete.employee_id); setConfirmDelete(null); }}
        onCancel={() => setConfirmDelete(null)}
      />

      {/* 员工状态机确认弹窗 */}
      {statusTarget && statusAction && (
        <ConfirmDialog
          open={!!statusTarget && !!statusAction}
          title="状态变更确认"
          message={`确定对员工「${statusTarget.name}」执行「${statusAction.label}」操作？`}
          confirmLabel={statusAction.label}
          danger={statusAction.danger}
          onConfirm={() => { if (statusTarget && statusAction) statusMutation.mutate({ emp: statusTarget, rpc: statusAction.rpc }); }}
          onCancel={() => { setStatusTarget(null); setStatusAction(null); }}
        />
      )}

      {/* 设上级弹窗 */}
      {managerTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">设置上级 · {managerTarget.name}</h3>
              <button onClick={() => { setManagerTarget(null); setManagerId(''); }} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">选择上级员工</label>
                <select value={managerId} onChange={(e) => setManagerId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]">
                  <option value="">请选择上级</option>
                  {peerOptions.map((p) => <option key={p.employee_id} value={p.employee_id}>{p.name} · {p.role_name}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => { setManagerTarget(null); setManagerId(''); }} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button onClick={() => { if (managerTarget && managerId) setManagerMutation.mutate({ emp: managerTarget, manager_employee_id: managerId }); }}
                disabled={!managerId || setManagerMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                {setManagerMutation.isPending ? '处理中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {(!data || data.length === 0) ? (
        <div className="text-center py-12 text-gray-400">
          <Users className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">暂无员工数据</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">姓名</th>
                  <th className="px-4 py-2 font-medium">角色</th>
                  <th className="px-4 py-2 font-medium">基座模型</th>
                  <th className="px-4 py-2 font-medium">状态</th>
                  <th className="px-4 py-2 font-medium w-20">操作</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((e) => (
                <tr key={e.employee_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-gray-800">{e.name}</td>
                  <td className="px-4 py-2.5 text-gray-600">{e.role_name}</td>
                  <td className="px-4 py-2.5 text-gray-500">
                    {e.template_id ? (
                      (() => {
                        const t = templateMap.get(e.template_id);
                        return t ? `${t.model} · ${t.provider_id || 'openai'}` : e.template_id;
                      })()
                    ) : '-'}
                  </td>
                  <td className="px-4 py-2.5"><StatusBadge status={e.status} /></td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1">
                      {(STATUS_ACTIONS[e.status] ?? []).map((a) => {
                        const Icon = a.icon;
                        return (
                          <button key={a.key} onClick={() => { setStatusTarget(e); setStatusAction(a); }}
                            className="p-1 text-gray-400 hover:text-blue-600" title={a.label}><Icon className="w-3.5 h-3.5" /></button>
                        );
                      })}
                      <button onClick={() => { setManagerTarget(e); setManagerId(''); }} className="p-1 text-gray-400 hover:text-blue-600" title="设上级"><UserCog className="w-3.5 h-3.5" /></button>
                      <button onClick={() => openEdit(e)} className="p-1 text-gray-400 hover:text-blue-600"><Pencil className="w-3.5 h-3.5" /></button>
                      <button onClick={() => setConfirmDelete(e)} className="p-1 text-gray-400 hover:text-red-600" title="删除"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
