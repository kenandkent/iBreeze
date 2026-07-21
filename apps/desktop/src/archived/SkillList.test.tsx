import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { SkillList } from './SkillList';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

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

const mockSkill = (overrides: Partial<Record<string, unknown>> = {}) => ({
  skill_id: 's1', company_scope: 'company', company_id: 'c1',
  name: 'Search', prompt_asset_id: 'pa1', prompt_asset_version: 1,
  tool_bindings: [{ tool_name: 'search', entrypoint: 'search.py', required_permissions: [], timeout: 30 }],
  knowledge_refs: [], input_schema: {}, output_schema: {}, checksum: 'abc',
  version: 2, status: 'draft', created_at: '', updated_at: '',
  ...overrides,
});

function getRowButtons(name: string) {
  const rows = screen.getAllByRole('row');
  const dataRow = rows.find(r => r.textContent?.includes(name));
  return dataRow!.querySelectorAll('button');
}

describe('SkillList', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders loading state', () => {
    mockInvoke.mockReturnValue(new Promise(() => {}));
    render(<SkillList companyId="c1" />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => expect(screen.getByText('暂无技能，点击右上角创建')).toBeInTheDocument());
  });

  it('renders skill list with all columns', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('Search')).toBeInTheDocument();
      expect(screen.getByText('公司')).toBeInTheDocument();
      expect(screen.getByText('v2')).toBeInTheDocument();
      expect(screen.getByText('草稿')).toBeInTheDocument();
    });
  });

  it('displays global scope label', async () => {
    mockInvoke.mockResolvedValue([mockSkill({ company_scope: 'global', company_id: null })]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => expect(screen.getByText('全局')).toBeInTheDocument());
  });

  it('displays all status labels', async () => {
    mockInvoke.mockResolvedValue([
      mockSkill({ skill_id: 's1', status: 'draft', name: 'D' }),
      mockSkill({ skill_id: 's2', status: 'published', name: 'P' }),
      mockSkill({ skill_id: 's3', status: 'deprecated', name: 'Dep' }),
      mockSkill({ skill_id: 's4', status: 'archived', name: 'Arch' }),
      mockSkill({ skill_id: 's5', status: 'review', name: 'Rev' }),
      mockSkill({ skill_id: 's6', status: 'unknown', name: 'Unk' }),
    ]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => {
      expect(screen.getByText('草稿')).toBeInTheDocument();
      expect(screen.getByText('已发布')).toBeInTheDocument();
      expect(screen.getByText('已弃用')).toBeInTheDocument();
      expect(screen.getByText('已归档')).toBeInTheDocument();
      expect(screen.getByText('评审中')).toBeInTheDocument();
      expect(screen.getByText('unknown')).toBeInTheDocument();
    });
  });

  it('passes companyId param', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId="comp-99" />);
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'cap.skill.list',
        params: JSON.stringify({ company_id: 'comp-99' }),
      }));
    });
  });

  it('loads without companyId when null', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId={null} />);
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'cap.skill.list',
        params: JSON.stringify({}),
      }));
    });
  });

  // --- Create ---
  it('opens create form', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('新建技能'));
    expect(screen.getByText('新建技能', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('技能名称')).toBeInTheDocument();
  });

  it('shows validation error with empty name', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('创建'));
    expect(screen.getByText('名称不能为空')).toBeInTheDocument();
  });

  it('calls rpcCall with correct params on create', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('新建技能'));
    fireEvent.change(screen.getByPlaceholderText('技能名称'), { target: { value: 'New Skill' } });
    fireEvent.change(screen.getByPlaceholderText('关联的 Prompt Asset'), { target: { value: 'prompt-xyz' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'cap.skill.create' }));
    });
    await waitFor(() => expect(screen.queryByPlaceholderText('技能名称')).not.toBeInTheDocument());
  });

  it('creates with global scope when companyId is null', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId={null} />);
    await waitFor(() => screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('新建技能'));
    fireEvent.change(screen.getByPlaceholderText('技能名称'), { target: { value: 'Global Skill' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => {
      const params = getCallParams('cap.skill.create');
      expect(params).toBeTruthy();
      expect(params.company_scope).toBe('global');
      expect(params.company_id).toBeNull();
    });
  });

  it('handles create error', async () => {
    mockInvoke.mockResolvedValueOnce([]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('新建技能'));
    fireEvent.change(screen.getByPlaceholderText('技能名称'), { target: { value: 'Fail' } });
    mockInvoke.mockRejectedValueOnce(new Error('create failed'));
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => expect(screen.getByText(/create failed/)).toBeInTheDocument());
  });

  it('cancel closes create form', async () => {
    mockInvoke.mockResolvedValue([]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('新建技能'));
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('技能名称')).not.toBeInTheDocument();
  });

  // --- Edit ---
  it('opens edit form pre-filled', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const editBtn = getRowButtons('Search')[0];
    fireEvent.click(editBtn);
    expect(screen.getByText('编辑技能')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Search')).toBeInTheDocument();
  });

  it('saves edited skill', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const editBtn = getRowButtons('Search')[0];
    fireEvent.click(editBtn);
    fireEvent.change(screen.getByDisplayValue('Search'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'cap.skill.update' })));
  });

  it('handles edit update error', async () => {
    mockInvoke.mockResolvedValueOnce([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const editBtn = getRowButtons('Search')[0];
    fireEvent.click(editBtn);
    mockInvoke.mockRejectedValueOnce(new Error('update failed'));
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => expect(screen.getByText(/update failed/)).toBeInTheDocument());
  });

  // --- Delete ---
  it('opens confirm dialog on delete', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const deleteBtn = getRowButtons('Search')[1];
    fireEvent.click(deleteBtn);
    expect(screen.getByText('确认删除')).toBeInTheDocument();
    expect(screen.getByText(/确定要归档技能「Search」/)).toBeInTheDocument();
  });

  it('archives skill on confirm', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const deleteBtn = getRowButtons('Search')[1];
    fireEvent.click(deleteBtn);
    fireEvent.click(screen.getByText('归档'));
    await waitFor(() => {
      const params = getCallParams('cap.skill.update');
      expect(params).toBeTruthy();
      expect(params.status).toBe('archived');
    });
  });

  it('handles delete error', async () => {
    mockInvoke.mockResolvedValueOnce([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const deleteBtn = getRowButtons('Search')[1];
    fireEvent.click(deleteBtn);
    mockInvoke.mockRejectedValueOnce(new Error('delete failed'));
    fireEvent.click(screen.getByText('归档'));
    await waitFor(() => {
      const params = getCallParams('cap.skill.update');
      expect(params).toBeTruthy();
      expect(params.status).toBe('archived');
    });
    expect(screen.getByText('确认删除')).toBeInTheDocument();
  });

  it('cancels delete dialog', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const deleteBtn = getRowButtons('Search')[1];
    fireEvent.click(deleteBtn);
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('确认删除')).not.toBeInTheDocument();
  });

  it('handles load error gracefully', async () => {
    mockInvoke.mockRejectedValue(new Error('network error'));
    render(<SkillList companyId="c1" />);
    await waitFor(() => expect(screen.queryByText('加载中...')).not.toBeInTheDocument());
    expect(screen.getByText('暂无技能，点击右上角创建')).toBeInTheDocument();
  });

  it('clicking 新建技能 switches from edit to create mode', async () => {
    mockInvoke.mockResolvedValue([mockSkill()]);
    render(<SkillList companyId="c1" />);
    await waitFor(() => screen.getByText('Search'));
    const editBtn = getRowButtons('Search')[0];
    fireEvent.click(editBtn);
    expect(screen.getByText('编辑技能')).toBeInTheDocument();
    fireEvent.click(screen.getByText('新建技能'));
    expect(screen.getByText('新建技能', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.queryByDisplayValue('Search')).not.toBeInTheDocument();
  });
});
