import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PromptList } from './PromptList';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const mockPrompt = (overrides: Partial<Record<string, unknown>> = {}) => ({
  prompt_asset_id: 'p1', company_scope: 'company', company_id: 'c1',
  name: 'Greeting', segments: { system: 'hi', developer: '', user_template: '', tool_instructions: '', output_contract: '' },
  variables: [{ name: 'x', type: 'string', required: true, default: '', validator: '' }],
  context_slots: ['conversation', 'knowledge'],
  checksum: 'abc', version: 2, status: 'draft',
  created_at: '', updated_at: '',
  ...overrides,
});

function findCall(method: string) {
  return mockInvoke.mock.calls.find((c: unknown[]) => {
    const opts = c[1] as Record<string, unknown> | undefined;
    return opts?.method === method;
  });
}

function getCallParams(method: string) {
  const call = findCall(method);
  if (!call) return null;
  const opts = call[1] as Record<string, string>;
  return JSON.parse(opts.params);
}

function getRowButtons(name: string) {
  const rows = screen.getAllByRole('row');
  const dataRow = rows.find(r => r.textContent?.includes(name));
  return dataRow!.querySelectorAll('button');
}

describe('PromptList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    mockInvoke.mockReturnValue(new Promise(() => {}));
    render(<PromptList companyId="c1" />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('暂无 Prompt 资产')).toBeInTheDocument();
    });
  });

  it('renders prompt list', async () => {
    mockInvoke.mockResolvedValue([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('Greeting')).toBeInTheDocument();
      expect(screen.getByText('公司')).toBeInTheDocument();
      expect(screen.getByText('v2')).toBeInTheDocument();
      expect(screen.getByText('草稿')).toBeInTheDocument();
    });
  });

  it('displays global scope', async () => {
    mockInvoke.mockResolvedValue([mockPrompt({ company_scope: 'global', company_id: null })]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('全局')).toBeInTheDocument();
    });
  });

  it('displays all status variants', async () => {
    mockInvoke.mockResolvedValue([
      mockPrompt({ prompt_asset_id: 'p1', status: 'draft', name: 'D' }),
      mockPrompt({ prompt_asset_id: 'p2', status: 'published', name: 'P' }),
      mockPrompt({ prompt_asset_id: 'p3', status: 'deprecated', name: 'Dep' }),
      mockPrompt({ prompt_asset_id: 'p4', status: 'archived', name: 'Arch' }),
      mockPrompt({ prompt_asset_id: 'p5', status: 'review', name: 'Rev' }),
      mockPrompt({ prompt_asset_id: 'p6', status: 'unknown', name: 'Unk' }),
    ]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('草稿')).toBeInTheDocument();
      expect(screen.getByText('已发布')).toBeInTheDocument();
      expect(screen.getByText('已弃用')).toBeInTheDocument();
      expect(screen.getByText('已归档')).toBeInTheDocument();
      expect(screen.getByText('评审中')).toBeInTheDocument();
      expect(screen.getByText('unknown')).toBeInTheDocument();
    });
  });

  // --- Create ---
  it('opens create form', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('新建'));
    fireEvent.click(screen.getByText('新建'));
    expect(screen.getByText('新建 Prompt')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Prompt 名称')).toBeInTheDocument();
  });

  it('validates empty name', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('新建'));
    fireEvent.click(screen.getByText('新建'));
    fireEvent.click(screen.getByText('创建'));
    expect(screen.getByText('名称不能为空')).toBeInTheDocument();
  });

  it('creates prompt with all fields', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('新建'));
    fireEvent.click(screen.getByText('新建'));

    fireEvent.change(screen.getByPlaceholderText('Prompt 名称'), { target: { value: 'New Prompt' } });
    fireEvent.change(screen.getByPlaceholderText('conversation,knowledge,memory'), { target: { value: 'memory' } });

    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => {
      const params = getCallParams('cap.prompt.create');
      expect(params).toBeTruthy();
      expect(params.name).toBe('New Prompt');
      expect(params.context_slots).toEqual(['memory']);
    });
  });

  it('handles create error', async () => {
    mockInvoke.mockResolvedValueOnce([]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('新建'));
    fireEvent.click(screen.getByText('新建'));
    fireEvent.change(screen.getByPlaceholderText('Prompt 名称'), { target: { value: 'X' } });
    mockInvoke.mockRejectedValueOnce(new Error('create err'));
    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => {
      expect(screen.getByText(/create err/)).toBeInTheDocument();
    });
  });

  it('cancel closes create form', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('新建'));
    fireEvent.click(screen.getByText('新建'));
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('Prompt 名称')).not.toBeInTheDocument();
  });

  // --- Edit ---
  it('opens edit form pre-filled', async () => {
    mockInvoke.mockResolvedValue([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const editBtn = getRowButtons('Greeting')[0];
    fireEvent.click(editBtn);

    expect(screen.getByText('编辑 Prompt')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Greeting')).toBeInTheDocument();
  });

  it('saves edited prompt', async () => {
    mockInvoke.mockResolvedValue([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const editBtn = getRowButtons('Greeting')[0];
    fireEvent.click(editBtn);

    fireEvent.change(screen.getByDisplayValue('Greeting'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'cap.prompt.update',
      }));
    });
  });

  it('handles update error', async () => {
    mockInvoke.mockResolvedValueOnce([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const editBtn = getRowButtons('Greeting')[0];
    fireEvent.click(editBtn);

    mockInvoke.mockRejectedValueOnce(new Error('upd err'));
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      expect(screen.getByText(/upd err/)).toBeInTheDocument();
    });
  });

  // --- Delete ---
  it('opens confirm dialog on delete', async () => {
    mockInvoke.mockResolvedValue([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const deleteBtn = getRowButtons('Greeting')[1];
    fireEvent.click(deleteBtn);

    expect(screen.getByText('确认归档')).toBeInTheDocument();
    expect(screen.getByText(/确定要归档 Prompt「Greeting」/)).toBeInTheDocument();
  });

  it('archives on confirm', async () => {
    mockInvoke.mockResolvedValue([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const deleteBtn = getRowButtons('Greeting')[1];
    fireEvent.click(deleteBtn);

    fireEvent.click(screen.getByText('归档'));

    await waitFor(() => {
      const params = getCallParams('cap.prompt.update');
      expect(params).toBeTruthy();
      expect(params.status).toBe('archived');
    });
  });

  it('handles delete error', async () => {
    mockInvoke.mockResolvedValueOnce([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const deleteBtn = getRowButtons('Greeting')[1];
    fireEvent.click(deleteBtn);

    mockInvoke.mockRejectedValueOnce(new Error('del err'));
    fireEvent.click(screen.getByText('归档'));

    await waitFor(() => {
      const params = getCallParams('cap.prompt.update');
      expect(params).toBeTruthy();
      expect(params.status).toBe('archived');
    });
    expect(screen.getByText('确认归档')).toBeInTheDocument();
  });

  it('cancels delete dialog', async () => {
    mockInvoke.mockResolvedValue([mockPrompt()]);
    render(<PromptList companyId="c1" />);
    await waitFor(() => screen.getByText('Greeting'));

    const deleteBtn = getRowButtons('Greeting')[1];
    fireEvent.click(deleteBtn);
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('确认归档')).not.toBeInTheDocument();
  });

  it('sends global scope when companyId is null', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<PromptList companyId={null} />);
    await waitFor(() => screen.getByText('新建'));
    fireEvent.click(screen.getByText('新建'));
    fireEvent.change(screen.getByPlaceholderText('Prompt 名称'), { target: { value: 'G' } });
    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => {
      const params = getCallParams('cap.prompt.create');
      expect(params).toBeTruthy();
      expect(params.company_scope).toBe('global');
    });
  });

  it('handles load error', async () => {
    mockInvoke.mockRejectedValue(new Error('load err'));
    render(<PromptList companyId="c1" />);
    await waitFor(() => {
      expect(screen.queryByText('加载中...')).not.toBeInTheDocument();
    });
    expect(screen.getByText('暂无 Prompt 资产')).toBeInTheDocument();
  });
});
