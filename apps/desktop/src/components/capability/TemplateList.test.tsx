import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { TemplateList } from './TemplateList';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const mockTemplate = (overrides: Partial<Record<string, unknown>> = {}) => ({
  template_id: 't1', template_scope: 'company', company_id: 'c1',
  provider_type: 'openai', provider_id: 'openai', model: 'gpt-4',
  capability_id: 'cap1', capability_version: 1,
  capability_snapshot: {}, default_role: 'Engineer',
  version: 2, status: 'draft',
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

describe('TemplateList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows no company message when companyId is null', () => {
    render(<TemplateList companyId={null} />);
    expect(screen.getByText('请先选择公司')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    mockInvoke.mockReturnValue(new Promise(() => {}));
    render(<TemplateList companyId="c1" />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('暂无模板')).toBeInTheDocument();
    });
  });

  it('renders template list', async () => {
    mockInvoke.mockResolvedValue([mockTemplate()]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('Engineer')).toBeInTheDocument();
      expect(screen.getByText('gpt-4')).toBeInTheDocument();
      expect(screen.getByText('v1')).toBeInTheDocument();
      expect(screen.getByText('草稿')).toBeInTheDocument();
    });
  });

  it('displays all status variants', async () => {
    mockInvoke.mockResolvedValue([
      mockTemplate({ template_id: 't1', status: 'draft', default_role: 'D' }),
      mockTemplate({ template_id: 't2', status: 'active', default_role: 'A' }),
      mockTemplate({ template_id: 't3', status: 'archived', default_role: 'Arch' }),
      mockTemplate({ template_id: 't4', status: 'unknown', default_role: 'Unk' }),
    ]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('草稿')).toBeInTheDocument();
      expect(screen.getByText('启用')).toBeInTheDocument();
      expect(screen.getByText('已归档')).toBeInTheDocument();
      expect(screen.getByText('unknown')).toBeInTheDocument();
    });
  });

  // --- Create ---
  it('opens create form', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('新建模板'));
    expect(screen.getByText('新建模板', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('关联的能力 ID')).toBeInTheDocument();
  });

  it('validates empty required fields', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('创建'));
    expect(screen.getByText('能力和角色名称不能为空')).toBeInTheDocument();
  });

  it('creates template with correct params', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('新建模板'));

    fireEvent.change(screen.getByPlaceholderText('关联的能力 ID'), { target: { value: 'cap-99' } });
    fireEvent.change(screen.getByPlaceholderText('如：高级工程师'), { target: { value: 'PM' } });
    fireEvent.change(screen.getByPlaceholderText('gpt-4'), { target: { value: 'gpt-3.5' } });

    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => {
      const params = getCallParams('org.template.create');
      expect(params).toBeTruthy();
      expect(params.capability_id).toBe('cap-99');
      expect(params.default_role).toBe('PM');
      expect(params.model).toBe('gpt-3.5');
    });
  });

  it('handles create error', async () => {
    mockInvoke.mockResolvedValueOnce([]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('新建模板'));
    fireEvent.change(screen.getByPlaceholderText('关联的能力 ID'), { target: { value: 'cap' } });
    fireEvent.change(screen.getByPlaceholderText('如：高级工程师'), { target: { value: 'R' } });
    mockInvoke.mockRejectedValueOnce(new Error('create err'));
    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => {
      expect(screen.getByText(/create err/)).toBeInTheDocument();
    });
  });

  it('cancel closes form', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('新建模板'));
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('关联的能力 ID')).not.toBeInTheDocument();
  });

  // --- Edit ---
  it('opens edit form pre-filled', async () => {
    mockInvoke.mockResolvedValue([mockTemplate()]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const editBtn = getRowButtons('Engineer')[0];
    fireEvent.click(editBtn);

    expect(screen.getByText('编辑模板')).toBeInTheDocument();
    expect(screen.getByDisplayValue('cap1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Engineer')).toBeInTheDocument();
    expect(screen.getByDisplayValue('gpt-4')).toBeInTheDocument();
  });

  it('saves edited template', async () => {
    mockInvoke.mockResolvedValue([mockTemplate()]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const editBtn = getRowButtons('Engineer')[0];
    fireEvent.click(editBtn);

    fireEvent.change(screen.getByDisplayValue('Engineer'), { target: { value: 'Senior' } });
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'org.template.update',
      }));
    });
  });

  it('handles update error', async () => {
    mockInvoke.mockResolvedValueOnce([mockTemplate()]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const editBtn = getRowButtons('Engineer')[0];
    fireEvent.click(editBtn);

    mockInvoke.mockRejectedValueOnce(new Error('upd err'));
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      expect(screen.getByText(/upd err/)).toBeInTheDocument();
    });
  });

  // --- Activate ---
  it('shows activate button for draft templates', async () => {
    mockInvoke.mockResolvedValue([mockTemplate({ status: 'draft' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    expect(buttons.length).toBe(2);
  });

  it('activates draft template', async () => {
    mockInvoke.mockResolvedValue([mockTemplate({ status: 'draft' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    fireEvent.click(buttons[1]);

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'org.template.activate',
      }));
    });
  });

  it('handles activate error', async () => {
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    mockInvoke.mockResolvedValueOnce([mockTemplate({ status: 'draft' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    mockInvoke.mockRejectedValueOnce(new Error('act err'));
    fireEvent.click(buttons[1]);

    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith(expect.stringContaining('act err'));
    });
    (window.alert as ReturnType<typeof vi.fn>).mockRestore();
  });

  // --- Archive ---
  it('shows archive button for active templates', async () => {
    mockInvoke.mockResolvedValue([mockTemplate({ status: 'active' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    expect(buttons.length).toBe(1);
  });

  it('archives active template', async () => {
    mockInvoke.mockResolvedValue([mockTemplate({ status: 'active' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'org.template.archive',
      }));
    });
  });

  it('handles archive error', async () => {
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    mockInvoke.mockResolvedValueOnce([mockTemplate({ status: 'active' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    mockInvoke.mockRejectedValueOnce(new Error('arch err'));
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith(expect.stringContaining('arch err'));
    });
    (window.alert as ReturnType<typeof vi.fn>).mockRestore();
  });

  it('no action buttons for archived templates', async () => {
    mockInvoke.mockResolvedValue([mockTemplate({ status: 'archived' })]);
    render(<TemplateList companyId="c1" />);
    await waitFor(() => screen.getByText('Engineer'));

    const buttons = getRowButtons('Engineer');
    expect(buttons.length).toBe(0);
  });

  it('handles load error gracefully', async () => {
    mockInvoke.mockRejectedValue(new Error('load err'));
    render(<TemplateList companyId="c1" />);
    await waitFor(() => {
      expect(screen.queryByText('加载中...')).not.toBeInTheDocument();
    });
    expect(screen.getByText('暂无模板')).toBeInTheDocument();
  });
});
