import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TaskBoard } from './TaskBoard';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

vi.mock('../../stores/appStore', () => ({
  useAppStore: () => ({
    currentCompanyId: 'c1',
    setCurrentCompany: vi.fn(),
  }),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockTask = (overrides: Partial<Record<string, unknown>> = {}) => ({
  task_id: 't1',
  company_id: 'c1',
  title: 'Test Task',
  description: 'A test task',
  status: 'created',
  priority: 5,
  version: 1,
  created_at: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('TaskBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText('暂无任务')).toBeInTheDocument();
    });
  });

  it('renders Kanban columns when there are tasks', async () => {
    mockInvoke.mockResolvedValue([mockTask()]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText(/待处理/)).toBeInTheDocument();
      expect(screen.getByText(/进行中/)).toBeInTheDocument();
      expect(screen.getByText(/已完成/)).toBeInTheDocument();
    });
  });

  it('places tasks in correct columns', async () => {
    mockInvoke.mockResolvedValue([
      mockTask({ task_id: 't1', title: 'Created Task', status: 'created' }),
      mockTask({ task_id: 't2', title: 'Running Task', status: 'running' }),
      mockTask({ task_id: 't3', title: 'Done Task', status: 'completed' }),
    ]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText('Created Task')).toBeInTheDocument();
      expect(screen.getByText('Running Task')).toBeInTheDocument();
      expect(screen.getByText('Done Task')).toBeInTheDocument();
    });

    const columns = screen.getAllByText(/\(\d+\)/);
    expect(columns[0]).toHaveTextContent('(1)');
    expect(columns[1]).toHaveTextContent('(1)');
    expect(columns[2]).toHaveTextContent('(1)');
  });

  it('opens and closes create dialog', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('暂无任务'));

    fireEvent.click(screen.getByText('新建任务'));
    expect(screen.getByText('新建任务', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入任务标题')).toBeInTheDocument();

    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('请输入任务标题')).not.toBeInTheDocument();
  });

  it('validates create form requires title', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('暂无任务'));

    fireEvent.click(screen.getByText('新建任务'));
    const submitBtn = screen.getByText('确认创建');
    expect(submitBtn).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('请输入任务标题'), { target: { value: 'New Task' } });
    expect(submitBtn).not.toBeDisabled();
  });

  it('creates task via rpcCall', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('暂无任务'));

    fireEvent.click(screen.getByText('新建任务'));
    fireEvent.change(screen.getByPlaceholderText('请输入任务标题'), { target: { value: 'New Task' } });
    fireEvent.change(screen.getByPlaceholderText('请输入任务描述（可选）'), { target: { value: 'desc' } });
    fireEvent.click(screen.getByText('确认创建'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'task.create',
      }));
    });
  });

  it('shows start button on created tasks and calls task.start', async () => {
    mockInvoke.mockResolvedValue([mockTask()]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('Test Task'));

    const startBtn = screen.getByTitle('开始任务');
    expect(startBtn).toBeInTheDocument();

    mockInvoke.mockResolvedValue(undefined);
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'task.start',
      }));
    });
  });

  it('does not show start button on running tasks', async () => {
    mockInvoke.mockResolvedValue([mockTask({ status: 'running' })]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('Test Task'));

    expect(screen.queryByTitle('开始任务')).not.toBeInTheDocument();
  });

  it('shows cancel button on created and running tasks', async () => {
    mockInvoke.mockResolvedValue([
      mockTask({ task_id: 't1', title: 'Task A', status: 'created' }),
      mockTask({ task_id: 't2', title: 'Task B', status: 'running' }),
    ]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText('Task A')).toBeInTheDocument();
      expect(screen.getByText('Task B')).toBeInTheDocument();
    });

    const cancelBtns = screen.getAllByTitle('取消任务');
    expect(cancelBtns).toHaveLength(2);
  });

  it('cancel opens ConfirmDialog and calls task.cancel on confirm', async () => {
    mockInvoke.mockResolvedValue([mockTask()]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('Test Task'));

    fireEvent.click(screen.getByTitle('取消任务'));
    expect(screen.getByText('确认取消')).toBeInTheDocument();
    expect(screen.getByText(/确定要取消任务「Test Task」/)).toBeInTheDocument();

    mockInvoke.mockResolvedValue(undefined);
    fireEvent.click(screen.getByText('取消任务', { selector: 'button' }));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'task.cancel',
      }));
    });
  });

  it('displays priority P1-P7', async () => {
    mockInvoke.mockResolvedValue([
      mockTask({ task_id: 't1', title: 'High', priority: 1 }),
      mockTask({ task_id: 't2', title: 'Low', priority: 7 }),
    ]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText('High')).toBeInTheDocument();
      expect(screen.getByText('Low')).toBeInTheDocument();
    });

    expect(screen.getByText('P1')).toBeInTheDocument();
    expect(screen.getByText('P7')).toBeInTheDocument();
  });

  it('renders error state with retry', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('load fail')));
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
      expect(screen.getByText('重试')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('retry button refetches on error', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('load fail')));
    renderWithQuery(<TaskBoard />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    }, { timeout: 5000 });

    mockInvoke.mockResolvedValue([mockTask()]);
    fireEvent.click(screen.getByText('重试'));

    await waitFor(() => {
      expect(screen.getByText('Test Task')).toBeInTheDocument();
    });
  });

  it('X button closes create dialog', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('暂无任务'));

    fireEvent.click(screen.getByText('新建任务'));
    expect(screen.getByText('新建任务', { selector: 'h3' })).toBeInTheDocument();

    const closeBtn = screen.getByText('新建任务', { selector: 'h3' }).closest('div')!.querySelector('button:last-child')!;
    fireEvent.click(closeBtn);
    expect(screen.queryByPlaceholderText('请输入任务标题')).not.toBeInTheDocument();
  });

  it('changing priority select updates form', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('暂无任务'));

    fireEvent.click(screen.getByText('新建任务'));

    const prioritySelect = screen.getByDisplayValue('P5 - 普通');
    fireEvent.change(prioritySelect, { target: { value: '1' } });
    expect(prioritySelect).toHaveValue('1');
  });

  it('ConfirmDialog cancel closes dialog', async () => {
    mockInvoke.mockResolvedValue([mockTask()]);
    renderWithQuery(<TaskBoard />);
    await waitFor(() => screen.getByText('Test Task'));

    fireEvent.click(screen.getByTitle('取消任务'));
    expect(screen.getByText('确认取消')).toBeInTheDocument();

    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('确认取消')).not.toBeInTheDocument();
  });
});
