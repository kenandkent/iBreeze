import { useState } from 'react';
import type { Task } from '../../types';
import { StatusBadge } from '../common/StatusBadge';
import { TaskDag } from './TaskDag';
import { GitBranch, Info } from 'lucide-react';

export function TaskDetail({ task }: { task: Task }) {
  const [tab, setTab] = useState<'info' | 'dag'>('info');

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-gray-800">{task.title}</h2>
        <StatusBadge status={task.status} />
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        <button
          onClick={() => setTab('info')}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
            tab === 'info'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Info size={14} />
          基本信息
        </button>
        <button
          onClick={() => setTab('dag')}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
            tab === 'dag'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <GitBranch size={14} />
          执行流程
        </button>
      </div>

      {tab === 'info' && (
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
      )}

      {tab === 'dag' && (
        <div className="border border-gray-200 rounded-lg overflow-hidden" style={{ height: 500 }}>
          <TaskDag taskId={task.task_id} />
        </div>
      )}
    </div>
  );
}
