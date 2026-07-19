import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TaskDetail } from './TaskDetail';
import type { Task } from '../../types';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const mockTask: Task = {
  task_id: 'task-001',
  company_id: 'comp-001',
  title: '测试任务',
  description: '这是一个测试任务',
  status: 'created',
  priority: 3,
  version: 1,
  created_at: '2025-01-15',
};

describe('TaskDetail', () => {
  it('renders task title', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('测试任务')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('created')).toBeInTheDocument();
  });

  it('renders priority', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('P3')).toBeInTheDocument();
  });

  it('renders created_at', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('2025-01-15')).toBeInTheDocument();
  });

  it('renders task ID', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('task-001')).toBeInTheDocument();
  });

  it('renders company ID', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('comp-001')).toBeInTheDocument();
  });

  it('renders section labels', () => {
    render(<TaskDetail task={mockTask} />);
    expect(screen.getByText('优先级')).toBeInTheDocument();
    expect(screen.getByText('创建时间')).toBeInTheDocument();
    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('所属公司')).toBeInTheDocument();
  });
});
