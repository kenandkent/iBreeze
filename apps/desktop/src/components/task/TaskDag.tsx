import { useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { LoadingSpinner } from '../common/LoadingSpinner';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface TaskNode {
  node_id: string;
  node_type: string;
  goal: string;
  status: string;
  depends_on: string[];
  assignee_employee_id?: string;
  generation_id?: string;
}

const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  created:    { bg: '#e0f2fe', border: '#0284c7', text: '#0c4a6e' },
  ready:      { bg: '#fef3c7', border: '#d97706', text: '#92400e' },
  running:    { bg: '#dcfce7', border: '#16a34a', text: '#166534' },
  completed:  { bg: '#f0fdf4', border: '#22c55e', text: '#14532d' },
  failed:     { bg: '#fef2f2', border: '#dc2626', text: '#991b1b' },
  cancelled:  { bg: '#f5f5f5', border: '#737373', text: '#525252' },
  dead_letter:{ bg: '#fef2f2', border: '#b91c1c', text: '#7f1d1d' },
};

const NODE_TYPE_LABELS: Record<string, string> = {
  agent_step:  'Agent',
  review_task: 'Review',
  fix:         'Fix',
  merge:       'Merge',
  manual_task: 'Manual',
  condition:   'Condition',
};

function buildLayout(nodes: TaskNode[]): { nodes: Node[]; edges: Edge[] } {
  if (!nodes.length) return { nodes: [], edges: [] };

  // Topological sort for y-position
  const idSet = new Set(nodes.map((n) => n.node_id));
  const inDegree = new Map<string, number>();
  const children = new Map<string, string[]>();
  for (const n of nodes) {
    inDegree.set(n.node_id, 0);
    children.set(n.node_id, []);
  }
  for (const n of nodes) {
    for (const dep of n.depends_on) {
      if (idSet.has(dep)) {
        inDegree.set(n.node_id, (inDegree.get(n.node_id) || 0) + 1);
        children.get(dep)?.push(n.node_id);
      }
    }
  }

  // BFS levels
  const levels = new Map<string, number>();
  const queue: string[] = [];
  for (const [id, deg] of inDegree) {
    if (deg === 0) {
      queue.push(id);
      levels.set(id, 0);
    }
  }
  while (queue.length) {
    const cur = queue.shift()!;
    const curLevel = levels.get(cur)!;
    for (const child of children.get(cur) || []) {
      const newLevel = curLevel + 1;
      if (!levels.has(child) || levels.get(child)! < newLevel) {
        levels.set(child, newLevel);
      }
      const deg = (inDegree.get(child) || 1) - 1;
      inDegree.set(child, deg);
      if (deg === 0) queue.push(child);
    }
  }
  // Fallback for disconnected nodes
  for (const n of nodes) {
    if (!levels.has(n.node_id)) levels.set(n.node_id, 0);
  }

  // Group by level for x-positioning
  const levelGroups = new Map<number, string[]>();
  for (const [id, level] of levels) {
    if (!levelGroups.has(level)) levelGroups.set(level, []);
    levelGroups.get(level)!.push(id);
  }

  const nodeById = new Map(nodes.map((n) => [n.node_id, n]));
  const X_GAP = 260;
  const Y_GAP = 120;

  const flowNodes: Node[] = [];
  for (const [level, ids] of levelGroups) {
    ids.forEach((id, idx) => {
      const n = nodeById.get(id)!;
      const colors = STATUS_COLORS[n.status] || STATUS_COLORS.created;
      flowNodes.push({
        id: n.node_id,
        position: { x: level * X_GAP, y: idx * Y_GAP },
        data: {
          label: (
            <div style={{ padding: 4, minWidth: 140 }}>
              <div style={{ fontWeight: 600, fontSize: 12, color: colors.text }}>
                {NODE_TYPE_LABELS[n.node_type] || n.node_type}
              </div>
              <div style={{ fontSize: 11, color: '#374151', marginTop: 2, lineHeight: 1.3 }}>
                {n.goal.length > 50 ? n.goal.slice(0, 50) + '...' : n.goal}
              </div>
              <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>
                {n.status}
                {n.assignee_employee_id && ` \u00B7 ${n.assignee_employee_id}`}
              </div>
            </div>
          ),
        },
        style: {
          background: colors.bg,
          border: `2px solid ${colors.border}`,
          borderRadius: 8,
          fontSize: 12,
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      });
    });
  }

  const flowEdges: Edge[] = [];
  for (const n of nodes) {
    for (const dep of n.depends_on) {
      if (idSet.has(dep)) {
        flowEdges.push({
          id: `${dep}->${n.node_id}`,
          source: dep,
          target: n.node_id,
          animated: n.status === 'running',
          markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
          style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        });
      }
    }
  }

  return { nodes: flowNodes, edges: flowEdges };
}

export function TaskDag({ taskId }: { taskId: string }) {
  const { data, isLoading, error } = useQuery<TaskNode[]>({
    queryKey: ['taskNodes', taskId],
    queryFn: () => rpcCall<TaskNode[]>('task.nodes', { task_id: taskId }),
    enabled: !!taskId,
    retry: 2,
  });

  const { nodes, edges } = useMemo(
    () => buildLayout(data || []),
    [data],
  );

  const onNodeClick = useCallback(() => {}, []);

  if (isLoading) return <LoadingSpinner />;
  if (error) return <div className="text-red-500 text-sm p-4">加载失败</div>;
  if (!nodes.length) return <div className="text-gray-400 text-sm p-4">暂无执行节点</div>;

  return (
    <div className="w-full h-full" style={{ minHeight: 400 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
