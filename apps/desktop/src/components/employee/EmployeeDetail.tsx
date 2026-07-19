import type { Employee } from '../../types';
import { StatusBadge } from '../common/StatusBadge';

export function EmployeeDetail({ employee }: { employee: Employee }) {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-gray-800">{employee.name}</h2>
        <StatusBadge status={employee.status} />
      </div>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-500">角色</span>
          <p className="text-gray-700 mt-0.5">{employee.role_name}</p>
        </div>
        <div>
          <span className="text-gray-500">类型</span>
          <p className="text-gray-700 mt-0.5">{employee.employee_type}</p>
        </div>
        <div>
          <span className="text-gray-500">ID</span>
          <p className="font-mono text-gray-700 mt-0.5">{employee.employee_id}</p>
        </div>
        <div>
          <span className="text-gray-500">所属公司</span>
          <p className="font-mono text-gray-700 mt-0.5">{employee.company_id}</p>
        </div>
      </div>
    </div>
  );
}
