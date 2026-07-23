import type { Task } from '../types';

interface TaskListProps {
  tasks: Task[];
  loading: boolean;
}

export function TaskList({ tasks, loading }: TaskListProps) {
  if (loading) {
    return <div className="p-4">Loading tasks...</div>;
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">Tasks</h2>
      {tasks.length === 0 ? (
        <p className="text-gray-500">No tasks yet.</p>
      ) : (
        <ul className="space-y-2">
          {tasks.map((task) => (
            <li key={task.id} className="p-3 border rounded-lg">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-medium">{task.title}</h3>
                  {task.description && <p className="text-sm text-gray-500">{task.description}</p>}
                </div>
                <span className={`px-2 py-1 text-xs rounded ${task.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                  {task.status}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
