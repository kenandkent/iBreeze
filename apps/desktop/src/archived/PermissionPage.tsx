import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { Network, ShieldCheck } from 'lucide-react';

interface Department {
  department_id: string;
  name: string;
  parent_department_id: string | null;
  leader_employee_id: string | null;
  status: string;
}

interface Employee {
  employee_id: string;
  name: string;
  department_id: string | null;
  employee_type: string;
  status: string;
}

interface GraphData {
  company_id: string;
  departments: Department[];
  employees: Employee[];
}

interface ResolveResult {
  company_id: string;
  employee_id: string;
  scope: Record<string, unknown>;
  scope_hash: string;
}

// 递归渲染部门树,root 为 parent_department_id 为空/null 的部门
function DepartmentTree({
  nodes,
  parentId,
  employeeName,
}: {
  nodes: Department[];
  parentId: string | null;
  employeeName: (id: string | null) => string;
}) {
  const children = nodes.filter((d) => (d.parent_department_id ?? null) === parentId);
  if (children.length === 0) return null;
  return (
    <ul className="pl-4 border-l border-gray-100">
      {children.map((d) => (
        <li key={d.department_id} className="py-1">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-800">{d.name}</span>
            <span className="text-xs text-gray-400">负责人: {employeeName(d.leader_employee_id)}</span>
            <StatusBadge status={d.status} />
          </div>
          <DepartmentTree nodes={nodes} parentId={d.department_id} employeeName={employeeName} />
        </li>
      ))}
    </ul>
  );
}

export function PermissionPage() {
  const { currentCompanyId } = useAppStore();
  const [selectedEmployee, setSelectedEmployee] = useState('');
  const [taskId, setTaskId] = useState('');
  const [resolveResult, setResolveResult] = useState<ResolveResult | null>(null);

  // 组织图
  const { data: graph, isLoading, error, refetch } = useQuery<GraphData>({
    queryKey: ['orgGraph', currentCompanyId],
    queryFn: async () => {
      const res = await rpcCall<GraphData>('org.graph.get', { company_id: currentCompanyId });
      return res;
    },
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  // 员工列表(用于选择要解析权限的员工)
  const { data: employees } = useQuery<Employee[]>({
    queryKey: ['orgEmployees', currentCompanyId],
    queryFn: async () => {
      const res = await rpcCall<Employee[]>('org.employee.list', { company_id: currentCompanyId });
      return res ?? [];
    },
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  // 权限解析
  const resolveMutation = useMutation({
    mutationFn: async () => {
      const params: Record<string, unknown> = { company_id: currentCompanyId, employee_id: selectedEmployee };
      if (taskId.trim()) params.task_id = taskId.trim();
      return rpcCall<ResolveResult>('org.permission.resolve', params);
    },
    onSuccess: (data) => setResolveResult(data),
  });

  if (!currentCompanyId) {
    return <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看权限可视化。</div>;
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    console.error('[iBreeze] PermissionPage: load failed', error);
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button onClick={() => refetch()} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700">重试</button>
      </div>
    );
  }

  const employeeName = (id: string | null) =>
    id ? employees?.find((e) => e.employee_id === id)?.name ?? id : '-';

  return (
    <div className="p-6 space-y-8">
      {/* 分区一:组织图 */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <Network className="w-5 h-5 text-gray-500" />
          <h2 className="text-base font-medium text-gray-700">组织图</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-sm font-medium text-gray-600 mb-3">部门结构</h3>
            {graph && graph.departments.length > 0 ? (
              <DepartmentTree nodes={graph.departments} parentId={null} employeeName={employeeName} />
            ) : (
              <p className="text-sm text-gray-400">暂无部门</p>
            )}
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-sm font-medium text-gray-600 mb-3">员工列表</h3>
            {graph && graph.employees.length > 0 ? (
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-500 text-left sticky top-0">
                    <tr>
                      <th className="px-3 py-2 font-medium">姓名</th>
                      <th className="px-3 py-2 font-medium">部门</th>
                      <th className="px-3 py-2 font-medium">类型</th>
                      <th className="px-3 py-2 font-medium">状态</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {graph.employees.map((e) => (
                      <tr key={e.employee_id} className="hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-800">{e.name}</td>
                        <td className="px-3 py-2 text-gray-600">
                          {graph.departments.find((d) => d.department_id === e.department_id)?.name ?? '-'}
                        </td>
                        <td className="px-3 py-2 text-gray-600">{e.employee_type}</td>
                        <td className="px-3 py-2"><StatusBadge status={e.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-400">暂无员工</p>
            )}
          </div>
        </div>
      </section>

      {/* 分区二:权限解析 */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <ShieldCheck className="w-5 h-5 text-gray-500" />
          <h2 className="text-base font-medium text-gray-700">权限解析</h2>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">选择员工</label>
              <select
                value={selectedEmployee}
                onChange={(e) => setSelectedEmployee(e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px] min-w-[200px]"
              >
                <option value="">请选择员工</option>
                {(employees ?? []).map((e) => (
                  <option key={e.employee_id} value={e.employee_id}>{e.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">任务 ID(可选)</label>
              <input
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
                placeholder="留空则解析整公司权限"
                className="px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
              />
            </div>
            <button
              onClick={() => resolveMutation.mutate()}
              disabled={!selectedEmployee || resolveMutation.isPending}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 h-[38px]"
            >
              {resolveMutation.isPending ? '解析中...' : '解析权限'}
            </button>
          </div>

          {resolveMutation.error && (
            <div className="text-red-500 text-sm">解析失败: {resolveMutation.error.message}</div>
          )}

          {resolveResult && (
            <div className="space-y-3">
              <div className="text-sm">
                <span className="text-gray-600">scope_hash: </span>
                <span className="font-mono text-gray-800 break-all">{resolveResult.scope_hash}</span>
              </div>
              <div>
                <div className="text-sm text-gray-600 mb-1">scope 内容</div>
                <pre className="text-xs bg-gray-50 border border-gray-100 rounded-md p-3 overflow-x-auto whitespace-pre-wrap break-all text-gray-800">
                  {JSON.stringify(resolveResult.scope, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
