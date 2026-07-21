import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { KnowledgeList } from './KnowledgeList';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockDoc = (overrides: Partial<Record<string, unknown>> = {}) => ({
  document_id: 'd1',
  company_id: 'c1',
  title: 'Test Doc',
  source_category: 'custom',
  status: 'active',
  ...overrides,
});

describe('KnowledgeList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('暂无文档')).toBeInTheDocument();
    });
  });

  it('renders knowledge list with title, category, status', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('Test Doc')).toBeInTheDocument();
      expect(screen.getByText('custom')).toBeInTheDocument();
      expect(screen.getByText('active')).toBeInTheDocument();
    });
  });

  it('opens and closes create dialog', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('暂无文档'));

    fireEvent.click(screen.getByText('添加文档'));
    expect(screen.getByText('添加文档', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入公司 ID')).toBeInTheDocument();

    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('请输入公司 ID')).not.toBeInTheDocument();
  });

  it('creates document with company_id, title, content, category', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('暂无文档'));

    fireEvent.click(screen.getByText('添加文档'));
    fireEvent.change(screen.getByPlaceholderText('请输入公司 ID'), { target: { value: 'c1' } });
    fireEvent.change(screen.getByPlaceholderText('请输入文档标题'), { target: { value: 'New Doc' } });
    fireEvent.change(screen.getByPlaceholderText('请输入文档内容'), { target: { value: 'Content here' } });

    fireEvent.click(screen.getByText('确认添加'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'knowledge.create',
      }));
    });
  });

  it('opens edit form with pre-filled values', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('Test Doc'));

    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);

    expect(screen.getByText('编辑文档')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Test Doc')).toBeInTheDocument();
  });

  it('saves edited document', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('Test Doc'));

    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);

    fireEvent.change(screen.getByDisplayValue('Test Doc'), { target: { value: 'Updated Doc' } });
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'knowledge.update',
      }));
    });
  });

  it('opens delete ConfirmDialog and confirms', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('Test Doc'));

    const row = screen.getByText('Test Doc').closest('tr')!;
    const trashBtn = row.querySelector('button:last-of-type')!;
    fireEvent.click(trashBtn);

    expect(screen.getByText('确认删除')).toBeInTheDocument();
    expect(screen.getByText(/确定要删除文档「Test Doc」/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '确认' }));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'knowledge.update',
      }));
    });
  });

  it('renders category filter options in create form', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('暂无文档'));

    fireEvent.click(screen.getByText('添加文档'));

    const select = screen.getByDisplayValue('自定义');
    fireEvent.change(select, { target: { value: 'policy' } });
    expect(select).toHaveValue('policy');

    fireEvent.change(select, { target: { value: 'technical' } });
    expect(select).toHaveValue('technical');

    fireEvent.change(select, { target: { value: 'training' } });
    expect(select).toHaveValue('training');
  });

  it('renders error state with retry', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('load fail')));
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
      expect(screen.getByText('重试')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('retry button refetches on error', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('load fail')));
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    }, { timeout: 5000 });

    mockInvoke.mockResolvedValue([mockDoc()]);
    fireEvent.click(screen.getByText('重试'));

    await waitFor(() => {
      expect(screen.getByText('Test Doc')).toBeInTheDocument();
    });
  });

  it('X button closes create modal', async () => {
    mockInvoke.mockResolvedValue([]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('暂无文档'));

    fireEvent.click(screen.getByText('添加文档'));
    expect(screen.getByText('添加文档', { selector: 'h3' })).toBeInTheDocument();

    const closeBtn = screen.getByText('添加文档', { selector: 'h3' }).closest('div')!.querySelector('button:last-child')!;
    fireEvent.click(closeBtn);
    expect(screen.queryByPlaceholderText('请输入公司 ID')).not.toBeInTheDocument();
  });

  it('X button closes edit modal', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('Test Doc'));

    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);
    expect(screen.getByText('编辑文档')).toBeInTheDocument();

    const closeBtn = screen.getByText('编辑文档').closest('div')!.querySelector('button:last-child')!;
    fireEvent.click(closeBtn);
    expect(screen.queryByText('编辑文档')).not.toBeInTheDocument();
  });

  it('handleEdit error does not crash', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('Test Doc'));

    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);

    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'knowledge.update') return Promise.reject(new Error('update fail'));
      return Promise.resolve([mockDoc()]);
    });

    fireEvent.change(screen.getByDisplayValue('Test Doc'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      expect(screen.getByText('编辑文档')).toBeInTheDocument();
    });
  });

  it('ConfirmDialog cancel closes dialog', async () => {
    mockInvoke.mockResolvedValue([mockDoc()]);
    renderWithQuery(<KnowledgeList />);
    await waitFor(() => screen.getByText('Test Doc'));

    const row = screen.getByText('Test Doc').closest('tr')!;
    const trashBtn = row.querySelector('button:last-of-type')!;
    fireEvent.click(trashBtn);

    expect(screen.getByText('确认删除')).toBeInTheDocument();
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('确认删除')).not.toBeInTheDocument();
  });
});
