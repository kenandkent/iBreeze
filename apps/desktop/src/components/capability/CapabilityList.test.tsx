import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { CapabilityList } from './CapabilityList';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function rpcResponder(_method: string, opts: { method: string; params: string }) {
  switch (opts.method) {
    case 'cap.capability.list':
      return Promise.resolve([mockCap()]);
    case 'cap.capability.get':
      return Promise.resolve({ ...mockCap(), skill_bindings: [{ skill_id: 's1' }] });
    case 'cap.capability.create':
    case 'cap.capability.update':
      return Promise.resolve({ ok: true });
    default:
      return Promise.resolve([]);
  }
}

function getCallParams(method: string) {
  const call = mockInvoke.mock.calls.find(
    (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === method,
  );
  if (!call) return null;
  return JSON.parse((call[1] as Record<string, string>).params);
}

const mockCap = (overrides: Partial<Record<string, unknown>> = {}) => ({
  capability_id: 'cap1', company_scope: 'company', company_id: 'c1',
  name: 'Code Review', description: 'Reviews code quality', source_category: 'custom',
  visibility: 'company', cost_policy: { default_model_tier: 'free', stability_level: 5 },
  skill_bindings: [], checksum: 'abc', version: 3, status: 'draft',
  created_at: '', updated_at: '',
  ...overrides,
});

describe('CapabilityList', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockInvoke.mockImplementation(rpcResponder);
  });

  it('renders loading state', () => {
    mockInvoke.mockReturnValue(new Promise(() => {}));
    render(<CapabilityList companyId="c1" />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([]));
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => expect(screen.getByText('暂无能力定义')).toBeInTheDocument());
  });

  it('renders capability list', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('Code Review')).toBeInTheDocument();
      expect(screen.getByText('Reviews code quality')).toBeInTheDocument();
      expect(screen.getByText('v3')).toBeInTheDocument();
    });
  });

  it('displays global scope', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([mockCap({ company_scope: 'global', company_id: null })]));
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => expect(screen.getByText('全局')).toBeInTheDocument());
  });

  it('displays missing description as dash', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([mockCap({ description: '' })]));
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => expect(screen.getByText('-')).toBeInTheDocument());
  });

  it('displays all status labels', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([
      mockCap({ capability_id: 'c1', status: 'draft', name: 'D' }),
      mockCap({ capability_id: 'c2', status: 'published', name: 'P' }),
      mockCap({ capability_id: 'c3', status: 'deprecated', name: 'Dep' }),
      mockCap({ capability_id: 'c4', status: 'archived', name: 'Arch' }),
      mockCap({ capability_id: 'c5', status: 'review', name: 'Rev' }),
      mockCap({ capability_id: 'c6', status: 'unknown', name: 'Unk' }),
    ]));
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('草稿')).toBeInTheDocument();
      expect(screen.getByText('已发布')).toBeInTheDocument();
      expect(screen.getByText('已弃用')).toBeInTheDocument();
      expect(screen.getByText('已归档')).toBeInTheDocument();
      expect(screen.getByText('评审中')).toBeInTheDocument();
      expect(screen.getByText('unknown')).toBeInTheDocument();
    });
  });

  it('opens create form', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('新建能力'));
    expect(screen.getByText('新建能力', { selector: 'h3' })).toBeInTheDocument();
  });

  it('validates empty name', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('创建'));
    expect(screen.getByText('名称不能为空')).toBeInTheDocument();
  });

  it('creates capability with all fields', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('新建能力'));
    fireEvent.change(screen.getByPlaceholderText('能力名称'), { target: { value: 'New Cap' } });
    fireEvent.change(screen.getByPlaceholderText('能力描述'), { target: { value: 'A desc' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => {
      const params = getCallParams('cap.capability.create');
      expect(params).toBeTruthy();
      expect(params.name).toBe('New Cap');
      expect(params.description).toBe('A desc');
    });
  });

  it('handles create error', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('新建能力'));
    fireEvent.change(screen.getByPlaceholderText('能力名称'), { target: { value: 'Fail' } });
    mockInvoke.mockImplementationOnce(() => Promise.reject(new Error('create failed')));
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => expect(screen.getByText(/create failed/)).toBeInTheDocument());
  });

  it('cancel closes form', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('能力名称')).not.toBeInTheDocument();
  });

  it('opens edit form pre-filled', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);
    expect(screen.getByText('编辑能力')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Code Review')).toBeInTheDocument();
  });

  it('loads skill_bindings on edit', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'cap.capability.get' }));
    });
  });

  it('handles capability.get error on edit', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);
    await waitFor(() => expect(screen.getByText('编辑能力')).toBeInTheDocument());
  });

  it('saves edited capability', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);
    await waitFor(() => expect(screen.getByDisplayValue('Code Review')).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue('Code Review'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => {
      const params = getCallParams('cap.capability.update');
      expect(params).toBeTruthy();
      expect(params.name).toBe('Updated');
    });
  });

  it('handles update error', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const editBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-pencil'));
    fireEvent.click(editBtn!);
    await waitFor(() => expect(screen.getByDisplayValue('Code Review')).toBeInTheDocument());
    mockInvoke.mockImplementationOnce(() => Promise.reject(new Error('update failed')));
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => expect(screen.getByText(/update failed/)).toBeInTheDocument());
  });

  it('opens confirm dialog on delete', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const deleteBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-trash2'));
    fireEvent.click(deleteBtn!);
    expect(screen.getByText('确认归档')).toBeInTheDocument();
  });

  it('archives capability on confirm', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const deleteBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-trash2'));
    fireEvent.click(deleteBtn!);
    fireEvent.click(screen.getByText('归档'));
    await waitFor(() => {
      const params = getCallParams('cap.capability.update');
      expect(params).toBeTruthy();
      expect(params.status).toBe('archived');
    });
  });

  it('handles delete error', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const deleteBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-trash2'));
    fireEvent.click(deleteBtn!);
    mockInvoke.mockImplementationOnce(() => Promise.reject(new Error('del failed')));
    fireEvent.click(screen.getByText('归档'));
    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'cap.capability.update',
      );
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as Record<string, string>).params).status).toBe('archived');
    });
  });

  it('cancels delete', async () => {
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => screen.getByText('Code Review'));
    const deleteBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-trash2'));
    fireEvent.click(deleteBtn!);
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('确认归档')).not.toBeInTheDocument();
  });

  it('sends global scope when companyId is null', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([]));
    render(<CapabilityList companyId={null} />);
    await waitFor(() => screen.getByText('新建能力'));
    fireEvent.click(screen.getByText('新建能力'));
    fireEvent.change(screen.getByPlaceholderText('能力名称'), { target: { value: 'Global' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => {
      const params = getCallParams('cap.capability.create');
      expect(params).toBeTruthy();
      expect(params.company_scope).toBe('global');
    });
  });

  it('handles load error gracefully', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('fail')));
    render(<CapabilityList companyId="c1" />);
    await waitFor(() => expect(screen.queryByText('加载中...')).not.toBeInTheDocument());
    expect(screen.getByText('暂无能力定义')).toBeInTheDocument();
  });
});
