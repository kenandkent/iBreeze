import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { useAppStore } from '../../stores/appStore';
import type { Company, Department, Employee } from '../../types';
import { Building2, X, Pencil, Trash2, ChevronRight, FolderTree, Plus, RotateCcw, Zap, UserCog, Move, Snowflake, Sun, Archive } from 'lucide-react';

const STATUS_OPTIONS = [
  { value: 'active', label: '正常运营' },
  { value: 'all', label: '全部' },
  { value: 'dissolved', label: '已解散' },
  { value: 'dissolving', label: '解散中' },
  { value: 'initializing', label: '初始化中' },
];

export function CompanyList() {
  const queryClient = useQueryClient();
  const { setCurrentCompany } = useAppStore();
  const [statusFilter, setStatusFilter] = useState('active');
  const [showCompanyModal, setShowCompanyModal] = useState(false);
  const [editCompany, setEditCompany] = useState<Company | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [companyForm, setCompanyForm] = useState({ name: '' });

  const [showDeptModal, setShowDeptModal] = useState(false);
  const [editDept, setEditDept] = useState<Department | null>(null);
  const [deptForm, setDeptForm] = useState({ name: '', description: '' });

  const [confirmTarget, setConfirmTarget] = useState<{ type: 'company' | 'department' | 'restore' | 'dissolve'; id: string; name: string } | null>(null);
  const [activateTarget, setActivateTarget] = useState<Company | null>(null);
  const [activateLeaderName, setActivateLeaderName] = useState('负责人');

  const { data: allCompanies, isLoading, error, refetch } = useQuery<Company[]>({
    queryKey: ['companies'],
    queryFn: () => rpcCall<Company[]>('org.company.list'),
    retry: 3,
    retryDelay: 1000,
  });

  const companies = allCompanies?.filter((c) => statusFilter === 'all' || c.status === statusFilter);

  const { data: departments } = useQuery<Department[]>({
    queryKey: ['departments', selectedCompany?.company_id],
    queryFn: () => rpcCall<Department[]>('org.department.list', { company_id: selectedCompany!.company_id }),
    enabled: !!selectedCompany,
  });

  const createCompany = useMutation({
    mutationFn: (name: string) => rpcCall('org.company.create', { name }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['companies'] }); closeCompanyModal(); },
  });

  const updateCompany = useMutation({
    mutationFn: ({ company_id, name }: { company_id: string; name: string }) => rpcCall('org.company.update', { company_id, name }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['companies'] }); closeCompanyModal(); },
  });

  const deleteCompany = useMutation({
    mutationFn: (company_id: string) => rpcCall('org.company.delete', { company_id }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['companies'] }); setSelectedCompany(null); setCurrentCompany(null); },
    onError: (err: Error) => alert('删除失败: ' + err.message),
  });

  const restoreCompany = useMutation({
    mutationFn: (company_id: string) => rpcCall('org.company.restore', { company_id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['companies'] }),
    onError: (err: Error) => alert('恢复失败: ' + err.message),
  });

  const dissolveCompany = useMutation({
    mutationFn: (company_id: string) => rpcCall('org.company.dissolve', { company_id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['companies'] }),
    onError: (err: Error) => alert('解散失败: ' + err.message),
  });

  const activateCompany = useMutation({
    mutationFn: ({ company_id, version, leader_name }: { company_id: string; version: number; leader_name: string }) =>
      rpcCall<{ company_id: string; status: string }>('org.company.activate', { company_id, expected_version: version, leader: { name: leader_name } }),
    onSuccess: (result: { company_id: string; status: string }) => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      if (result.status === 'active') {
        setCurrentCompany(result.company_id);
      }
      setActivateTarget(null);
      setActivateLeaderName('负责人');
    },
    onError: (err: Error) => alert('激活失败: ' + err.message),
  });

  const createDept = useMutation({
    mutationFn: (data: { company_id: string; name: string; description: string }) => rpcCall('org.department.create', data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['departments', selectedCompany?.company_id] }); closeDeptModal(); },
  });

  const updateDept = useMutation({
    mutationFn: ({ department_id, name, description }: { department_id: string; name: string; description: string }) =>
      rpcCall('org.department.update', { department_id, name, description }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['departments', selectedCompany?.company_id] }); closeDeptModal(); },
  });

  const deleteDept = useMutation({
    mutationFn: (department_id: string) => rpcCall('org.department.delete', { department_id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['departments', selectedCompany?.company_id] }),
    onError: (err: Error) => alert('删除部门失败: ' + err.message),
  });

  // 部门高级操作：设负责人 / 移动 / 冻结 / 解冻
  const setLeaderMutation = useMutation({
    mutationFn: ({ department_id, leader_employee_id }: { department_id: string; leader_employee_id: string }) =>
      rpcCall('org.department.setLeader', { department_id, leader_employee_id }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['departments', selectedCompany?.company_id] }); setLeaderTarget(null); setLeaderId(''); },
    onError: (err: Error) => alert('设置负责人失败: ' + err.message),
  });

  const moveDeptMutation = useMutation({
    mutationFn: ({ department_id, new_parent_department_id }: { department_id: string; new_parent_department_id: string | null }) =>
      rpcCall('org.department.move', { department_id, new_parent_department_id }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['departments', selectedCompany?.company_id] }); setMoveTarget(null); setMoveParentId(''); },
    onError: (err: Error) => alert('移动部门失败: ' + err.message),
  });

  const freezeDeptMutation = useMutation({
    mutationFn: ({ department_id, freeze }: { department_id: string; freeze: boolean }) =>
      rpcCall(freeze ? 'org.department.freeze' : 'org.department.unfreeze', { department_id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['departments', selectedCompany?.company_id] }),
    onError: (err: Error) => alert('操作失败: ' + err.message),
  });

  // 设负责人弹窗状态
  const [leaderTarget, setLeaderTarget] = useState<Department | null>(null);
  const [leaderId, setLeaderId] = useState('');
  // 移动弹窗状态
  const [moveTarget, setMoveTarget] = useState<Department | null>(null);
  const [moveParentId, setMoveParentId] = useState('');
  // 冻结确认弹窗状态
  const [freezeTarget, setFreezeTarget] = useState<{ dept: Department; freeze: boolean } | null>(null);

  // 设负责人可用的同公司员工
  const { data: deptEmployees } = useQuery<Employee[]>({
    queryKey: ['employees', 'company', selectedCompany?.company_id],
    queryFn: () => rpcCall<Employee[]>('org.employee.list'),
    enabled: !!leaderTarget && !!selectedCompany,
  });
  const leaderOptions = (deptEmployees ?? []).filter((e) => !selectedCompany || e.company_id === selectedCompany.company_id);

  // 移动可用的候选父部门（排除自身及子孙，简单排除自身）
  const moveParentOptions = (departments ?? []).filter((d) => d.department_id !== moveTarget?.department_id);

  function handleConfirm() {
    if (!confirmTarget) return;
    if (confirmTarget.type === 'company') deleteCompany.mutate(confirmTarget.id);
    else if (confirmTarget.type === 'department') deleteDept.mutate(confirmTarget.id);
    else if (confirmTarget.type === 'restore') restoreCompany.mutate(confirmTarget.id);
    else if (confirmTarget.type === 'dissolve') dissolveCompany.mutate(confirmTarget.id);
    setConfirmTarget(null);
  }

  function closeCompanyModal() { setShowCompanyModal(false); setEditCompany(null); setCompanyForm({ name: '' }); }
  function closeDeptModal() { setShowDeptModal(false); setEditDept(null); setDeptForm({ name: '', description: '' }); }

  if (isLoading) return <LoadingSpinner />;
  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  const confirmTitle = confirmTarget?.type === 'restore' ? '恢复' : confirmTarget?.type === 'dissolve' ? '解散' : '删除';
  const confirmMsg = confirmTarget?.type === 'company' ? `确定删除公司「${confirmTarget.name}」？所有部门和员工将一并删除。`
    : confirmTarget?.type === 'department' ? `确定删除部门「${confirmTarget.name}」？`
    : confirmTarget?.type === 'restore' ? `确定恢复公司「${confirmTarget.name}」？`
    : confirmTarget?.type === 'dissolve' ? `确定解散公司「${confirmTarget.name}」？解散后状态变为「解散中」，可通过恢复撤销。`
    : '';

  return (
    <div className="flex h-full">
      {/* 左侧公司列表 */}
      <div className="w-64 border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium text-gray-700">公司列表</h2>
            <button onClick={() => { setCompanyForm({ name: '' }); setEditCompany(null); setShowCompanyModal(true); }} className="text-blue-600 hover:text-blue-700">
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setSelectedCompany(null); setCurrentCompany(null); }}
            className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div className="flex-1 overflow-y-auto">
          {!companies || companies.length === 0 ? (
            <div className="p-4 text-center text-gray-400 text-sm">暂无公司</div>
          ) : (
            companies.map((company) => (
              <div
                key={company.company_id}
                className={`px-4 py-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors ${
                  selectedCompany?.company_id === company.company_id ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
                }`}
                onClick={() => { setSelectedCompany(company); setCurrentCompany(company.company_id); }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <Building2 className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    <span className="text-sm text-gray-700 truncate">{company.name}</span>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {company.status === 'initializing' ? (
                      <button onClick={(e) => { e.stopPropagation(); setActivateTarget(company); setActivateLeaderName('负责人'); }} className="p-1 text-gray-400 hover:text-green-600" title="激活">
                        <Zap className="w-3.5 h-3.5" />
                      </button>
                    ) : company.status !== 'active' ? (
                      <button onClick={(e) => { e.stopPropagation(); setConfirmTarget({ type: 'restore', id: company.company_id, name: company.name }); }} className="p-1 text-gray-400 hover:text-green-600" title="恢复">
                        <RotateCcw className="w-3.5 h-3.5" />
                      </button>
                    ) : (
                      <>
                        <button onClick={(e) => { e.stopPropagation(); setCompanyForm({ name: company.name }); setEditCompany(company); setShowCompanyModal(true); }} className="p-1 text-gray-400 hover:text-blue-600">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); setConfirmTarget({ type: 'company', id: company.company_id, name: company.name }); }} className="p-1 text-gray-400 hover:text-red-600" title="删除">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); setConfirmTarget({ type: 'dissolve', id: company.company_id, name: company.name }); }} className="p-1 text-gray-400 hover:text-amber-600" title="解散">
                          <Archive className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-gray-300" />
                  </div>
                </div>
                <div className="mt-1"><StatusBadge status={company.status} /></div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 右侧部门区域 */}
      <div className="flex-1 flex flex-col">
        {selectedCompany ? (
          <>
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-gray-500" />
                <h3 className="text-sm font-medium text-gray-700">{selectedCompany.name} - 部门</h3>
              </div>
              {selectedCompany.status === 'active' && (
                <button onClick={() => { setDeptForm({ name: '', description: '' }); setEditDept(null); setShowDeptModal(true); }} className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700">
                  新建部门
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {!departments || departments.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                  <FolderTree className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  <p className="text-sm">暂无部门</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {departments.map((dept) => (
                    <div key={dept.department_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-700">{dept.name}</div>
                        {dept.description && <div className="text-xs text-gray-500 mt-0.5">{dept.description}</div>}
                      </div>
                      {selectedCompany.status === 'active' && (
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button onClick={() => { setLeaderTarget(dept); setLeaderId(''); }} className="p-1 text-gray-400 hover:text-blue-600" title="设负责人"><UserCog className="w-3.5 h-3.5" /></button>
                          <button onClick={() => { setMoveTarget(dept); setMoveParentId(dept.parent_department_id ?? ''); }} className="p-1 text-gray-400 hover:text-blue-600" title="移动"><Move className="w-3.5 h-3.5" /></button>
                          <button onClick={() => setFreezeTarget({ dept, freeze: dept.status !== 'frozen' })} className="p-1 text-gray-400 hover:text-amber-600" title={dept.status === 'frozen' ? '解冻' : '冻结'}>
                            {dept.status === 'frozen' ? <Sun className="w-3.5 h-3.5" /> : <Snowflake className="w-3.5 h-3.5" />}
                          </button>
                          <button onClick={() => { setDeptForm({ name: dept.name, description: dept.description || '' }); setEditDept(dept); setShowDeptModal(true); }} className="p-1 text-gray-400 hover:text-blue-600">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => setConfirmTarget({ type: 'department', id: dept.department_id, name: dept.name })} className="p-1 text-gray-400 hover:text-red-600" title="删除">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">选择左侧公司查看部门</div>
        )}
      </div>

      {/* 二次确认弹窗 */}
      <ConfirmDialog
        open={!!confirmTarget}
        title={`${confirmTitle}确认`}
        message={confirmMsg}
        confirmLabel={confirmTitle}
        danger={confirmTarget?.type !== 'restore'}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmTarget(null)}
      />

      {/* 公司创建/编辑弹窗 */}
      {showCompanyModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">{editCompany ? '编辑公司' : '新建公司'}</h3>
              <button onClick={closeCompanyModal} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">公司名称</label>
                <input type="text" value={companyForm.name} onChange={(e) => setCompanyForm({ name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" placeholder="请输入公司名称" autoFocus />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={closeCompanyModal} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button onClick={() => editCompany ? updateCompany.mutate({ company_id: editCompany.company_id, name: companyForm.name }) : createCompany.mutate(companyForm.name)}
                disabled={!companyForm.name || createCompany.isPending || updateCompany.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                {createCompany.isPending || updateCompany.isPending ? '处理中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 部门创建/编辑弹窗 */}
      {showDeptModal && selectedCompany && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">{editDept ? '编辑部门' : '新建部门'}</h3>
              <button onClick={closeDeptModal} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">部门名称</label>
                <input type="text" value={deptForm.name} onChange={(e) => setDeptForm({ ...deptForm, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" placeholder="请输入部门名称" autoFocus />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">描述</label>
                <textarea value={deptForm.description} onChange={(e) => setDeptForm({ ...deptForm, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" placeholder="可选" rows={2} />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={closeDeptModal} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button onClick={() => editDept
                ? updateDept.mutate({ department_id: editDept.department_id, name: deptForm.name, description: deptForm.description })
                : createDept.mutate({ company_id: selectedCompany.company_id, name: deptForm.name, description: deptForm.description })}
                disabled={!deptForm.name || createDept.isPending || updateDept.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                {createDept.isPending || updateDept.isPending ? '处理中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 部门设负责人弹窗 */}
      {leaderTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">设置负责人 · {leaderTarget.name}</h3>
              <button onClick={() => { setLeaderTarget(null); setLeaderId(''); }} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">选择负责人员工</label>
                <select value={leaderId} onChange={(e) => setLeaderId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]">
                  <option value="">请选择员工</option>
                  {leaderOptions.map((e) => <option key={e.employee_id} value={e.employee_id}>{e.name} · {e.role_name}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => { setLeaderTarget(null); setLeaderId(''); }} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button onClick={() => { if (leaderTarget && leaderId) setLeaderMutation.mutate({ department_id: leaderTarget.department_id, leader_employee_id: leaderId }); }}
                disabled={!leaderId || setLeaderMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                {setLeaderMutation.isPending ? '处理中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 部门移动弹窗 */}
      {moveTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">移动部门 · {moveTarget.name}</h3>
              <button onClick={() => { setMoveTarget(null); setMoveParentId(''); }} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">新父部门</label>
                <select value={moveParentId} onChange={(e) => setMoveParentId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]">
                  <option value="">顶级部门（无上级）</option>
                  {moveParentOptions.map((d) => <option key={d.department_id} value={d.department_id}>{d.name}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => { setMoveTarget(null); setMoveParentId(''); }} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button onClick={() => { if (moveTarget) moveDeptMutation.mutate({ department_id: moveTarget.department_id, new_parent_department_id: moveParentId || null }); }}
                disabled={moveDeptMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                {moveDeptMutation.isPending ? '处理中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 部门冻结/解冻确认弹窗 */}
      <ConfirmDialog
        open={!!freezeTarget}
        title={freezeTarget?.freeze ? '冻结确认' : '解冻确认'}
        message={freezeTarget ? `确定${freezeTarget.freeze ? '冻结' : '解冻'}部门「${freezeTarget.dept.name}」？` : ''}
        confirmLabel={freezeTarget?.freeze ? '冻结' : '解冻'}
        onConfirm={() => { if (freezeTarget) freezeDeptMutation.mutate({ department_id: freezeTarget.dept.department_id, freeze: freezeTarget.freeze }); setFreezeTarget(null); }}
        onCancel={() => setFreezeTarget(null)}
      />

      {/* 激活公司弹窗 */}
      {activateTarget && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">激活公司「{activateTarget.name}」</h3>
              <button onClick={() => setActivateTarget(null)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-sm text-gray-500 mb-4">激活后公司状态将变为「正常运营」，并创建首任负责人。</p>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">负责人姓名</label>
                <input type="text" value={activateLeaderName} onChange={(e) => setActivateLeaderName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400" placeholder="请输入负责人姓名" autoFocus />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setActivateTarget(null)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => activateCompany.mutate({ company_id: activateTarget.company_id, version: activateTarget.version, leader_name: activateLeaderName })}
                disabled={!activateLeaderName || activateCompany.isPending}
                className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50">
                {activateCompany.isPending ? '激活中...' : '确认激活'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
