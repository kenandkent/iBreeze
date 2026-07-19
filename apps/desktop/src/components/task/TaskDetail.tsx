import type { Task } from '../../types';
import { StatusBadge } from '../common/StatusBadge';

export function TaskDetail({ task }: { task: Task }) {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-gray-800">{task.title}</h2>
        <StatusBadge status={task.status} />
      </div>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-500">优先级</span>
          <p className="text-gray-700 mt-0.5">P{task.priority}</p>
        </div>
        <div>
          <span className="text-gray-500">创建时间</span>
          <p className="text-gray-700 mt-0.5">{task.created_at}</p>
        </div>
        <div>
          <span className="text-gray-500">ID</span>
          <p className="font-mono text-gray-700 mt-0.5">{task.task_id}</p>
        </div>
        <div>
          <span className="text-gray-500">所属公司</span>
          <p className="font-mono text-gray-700 mt-0.5">{task.company_id}</p>
        </div>
      </div>
    </div>
  );
}
