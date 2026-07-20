import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CompanyList } from './CompanyList';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockCompany = (overrides: Partial<Record<string, unknown>> = {}) => ({
  company_id: 'c1', name: 'Test Corp', status: 'active', created_at: '2024-01-01',
  ...overrides,
});

const mockDept = (overrides: Partial<Record<string, unknown>> = {}) => ({
  department_id: 'd1', company_id: 'c1', parent_department_id: null,
  name: 'Engineering', description: 'Eng dept', status: 'active', created_at: '2024-01-01',
  ...overrides,
});

function defaultResponder(_method: string, opts: { method: string }) {
  switch (opts.method) {
    case 'org.company.list':
      return Promise.resolve([mockCompany()]);
    case 'org.department.list':
      return Promise.resolve([mockDept()]);
    default:
      return Promise.resolve({ ok: true });
  }
}

describe('CompanyList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockInvoke.mockImplementation(defaultResponder);
  });

  it('renders loading state', () => {
    mockInvoke.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<CompanyList />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders error state with retry button', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('Network error')));
    renderWithQuery(<CompanyList />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
      expect(screen.getByText('重试')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders empty company list', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => {
      expect(screen.getByText('暂无公司')).toBeInTheDocument();
    });
  });

  it('renders placeholder when no company selected', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => {
      expect(screen.getByText('选择左侧公司查看部门')).toBeInTheDocument();
    });
  });

  it('renders companies', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument();
    });
  });

  it('filters companies by status', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([
      mockCompany({ company_id: 'c1', name: 'Active', status: 'active' }),
      mockCompany({ company_id: 'c2', name: 'Dissolved', status: 'dissolved' }),
    ]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.queryByText('Dissolved')).not.toBeInTheDocument();
    });
  });

  it('shows all companies when filter is "all"', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([
      mockCompany({ company_id: 'c1', name: 'Active', status: 'active' }),
      mockCompany({ company_id: 'c2', name: 'Dissolved', status: 'dissolved' }),
    ]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Active'));

    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Dissolved')).toBeInTheDocument();
    });
  });

  it('deselects company when filter changes', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([
      mockCompany({ company_id: 'c1', name: 'Active', status: 'active' }),
    ]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Active'));

    fireEvent.click(screen.getByText('Active'));
    await waitFor(() => {
      expect(screen.getByText('Active - 部门')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => {
      expect(screen.queryByText('Active - 部门')).not.toBeInTheDocument();
    });
  });

  it('loads departments when company selected', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => {
      expect(screen.getByText('Test Corp - 部门')).toBeInTheDocument();
      expect(screen.getByText('Engineering')).toBeInTheDocument();
      expect(screen.getByText('Eng dept')).toBeInTheDocument();
    });
  });

  it('shows empty departments', async () => {
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.department.list') return Promise.resolve([]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => {
      expect(screen.getByText('暂无部门')).toBeInTheDocument();
    });
  });

  it('opens company create modal', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('公司列表'));

    const plusBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-plus'));
    fireEvent.click(plusBtn!);

    expect(screen.getByText('新建公司')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入公司名称')).toBeInTheDocument();
  });

  it('creates company', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('公司列表'));

    const plusBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-plus'));
    fireEvent.click(plusBtn!);

    fireEvent.change(screen.getByPlaceholderText('请输入公司名称'), { target: { value: 'New Corp' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.company.create',
      );
      expect(call).toBeTruthy();
    });
  });

  it('cancel closes company modal', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('公司列表'));

    const plusBtn = screen.getAllByRole('button').find(b => b.querySelector('.lucide-plus'));
    fireEvent.click(plusBtn!);
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('请输入公司名称')).not.toBeInTheDocument();
  });

  it('opens edit company modal', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const pencilBtn = companyItem.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);

    expect(screen.getByText('编辑公司')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Test Corp')).toBeInTheDocument();
  });

  it('updates company', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const pencilBtn = companyItem.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);

    fireEvent.change(screen.getByDisplayValue('Test Corp'), { target: { value: 'Updated Corp' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.company.update',
      );
      expect(call).toBeTruthy();
    });
  });

  it('opens delete confirm for active company', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const trashBtn = companyItem.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);

    expect(screen.getByText('删除确认')).toBeInTheDocument();
    expect(screen.getByText(/确定删除公司「Test Corp」/)).toBeInTheDocument();
  });

  it('opens dissolve confirm for active company', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const dissolveBtn = companyItem.querySelector('.lucide-archive')?.closest('button');
    fireEvent.click(dissolveBtn!);

    expect(screen.getByText('解散')).toBeInTheDocument();
    expect(screen.getByText(/确定解散公司「Test Corp」/)).toBeInTheDocument();
  });

  it('deletes company on confirm', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const trashBtn = companyItem.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);
    fireEvent.click(screen.getByText('删除'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.company.delete',
      );
      expect(call).toBeTruthy();
    });
  });

  it('shows restore button for non-active company', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([mockCompany({ status: 'dissolved' })]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByDisplayValue('正常运营'));
    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument();
    });
    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    expect(companyItem.querySelector('.lucide-rotate-ccw')).toBeTruthy();
  });

  it('restores company', async () => {
    mockInvoke.mockImplementation(() => Promise.resolve([mockCompany({ status: 'dissolved' })]));
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByDisplayValue('正常运营'));
    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const restoreBtn = companyItem.querySelector('.lucide-rotate-ccw')?.closest('button');
    fireEvent.click(restoreBtn!);

    expect(screen.getByText('恢复确认')).toBeInTheDocument();
    expect(screen.getByText(/确定恢复公司「Test Corp」/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('恢复'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.company.restore',
      );
      expect(call).toBeTruthy();
    });
  });

  it('opens dept create modal', async () => {
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.department.list') return Promise.resolve([]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('暂无部门'));

    fireEvent.click(screen.getByText('新建部门'));
    expect(screen.getByText('新建部门', { selector: 'h3' })).toBeInTheDocument();
  });

  it('creates department', async () => {
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.department.list') return Promise.resolve([]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('暂无部门'));

    fireEvent.click(screen.getByText('新建部门'));
    fireEvent.change(screen.getByPlaceholderText('请输入部门名称'), { target: { value: 'Sales' } });
    fireEvent.change(screen.getByPlaceholderText('可选'), { target: { value: 'Sales team' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.department.create',
      );
      expect(call).toBeTruthy();
    });
  });

  it('cancels dept modal', async () => {
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.department.list') return Promise.resolve([]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('暂无部门'));

    fireEvent.click(screen.getByText('新建部门'));
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('请输入部门名称')).not.toBeInTheDocument();
  });

  it('opens dept edit modal', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('Engineering'));

    const deptItem = screen.getByText('Engineering').closest('[class*="bg-gray-50"]')!;
    const pencilBtn = deptItem.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);

    expect(screen.getByText('编辑部门')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Engineering')).toBeInTheDocument();
  });

  it('updates department', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('Engineering'));

    const deptItem = screen.getByText('Engineering').closest('[class*="bg-gray-50"]')!;
    const pencilBtn = deptItem.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);

    fireEvent.change(screen.getByDisplayValue('Engineering'), { target: { value: 'Sales' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.department.update',
      );
      expect(call).toBeTruthy();
    });
  });

  it('deletes department', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('Engineering'));

    const deptItem = screen.getByText('Engineering').closest('[class*="bg-gray-50"]')!;
    const trashBtn = deptItem.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);

    expect(screen.getByText('删除确认')).toBeInTheDocument();
    expect(screen.getByText(/确定删除部门「Engineering」/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('删除'));

    await waitFor(() => {
      const call = mockInvoke.mock.calls.find(
        (c: unknown[]) => (c[1] as Record<string, unknown>)?.method === 'org.department.delete',
      );
      expect(call).toBeTruthy();
    });
  });

  it('does not show new dept button for non-active company', async () => {
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.company.list') return Promise.resolve([mockCompany({ status: 'dissolved' })]);
      if (opts.method === 'org.department.list') return Promise.resolve([]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByDisplayValue('正常运营'));
    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => {
      expect(screen.queryByText('新建部门')).not.toBeInTheDocument();
    });
  });

  it('does not show dept action buttons for non-active company', async () => {
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.company.list') return Promise.resolve([mockCompany({ status: 'dissolved' })]);
      if (opts.method === 'org.department.list') return Promise.resolve([mockDept()]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByDisplayValue('正常运营'));
    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => {
      expect(screen.getByText('Engineering')).toBeInTheDocument();
    });
    const deptItem = screen.getByText('Engineering').closest('[class*="bg-gray-50"]')!;
    expect(deptItem.querySelector('.lucide-pencil')).toBeFalsy();
    expect(deptItem.querySelector('.lucide-trash2')).toBeFalsy();
  });

  it('cancel dept edit closes modal', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('Engineering'));

    const deptItem = screen.getByText('Engineering').closest('[class*="bg-gray-50"]')!;
    const pencilBtn = deptItem.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByDisplayValue('Engineering')).not.toBeInTheDocument();
  });

  it('handles delete company error', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    let callCount = 0;
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.company.delete') {
        callCount++;
        return Promise.reject(new Error('delete failed'));
      }
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const trashBtn = companyItem.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);
    fireEvent.click(screen.getByText('删除'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('删除失败: delete failed');
    });
    alertSpy.mockRestore();
  });

  it('handles restore company error', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.company.restore') return Promise.reject(new Error('restore failed'));
      if (opts.method === 'org.company.list') return Promise.resolve([mockCompany({ status: 'dissolved' })]);
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByDisplayValue('正常运营'));
    fireEvent.change(screen.getByDisplayValue('正常运营'), { target: { value: 'all' } });
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const restoreBtn = companyItem.querySelector('.lucide-rotate-ccw')?.closest('button');
    fireEvent.click(restoreBtn!);
    fireEvent.click(screen.getByText('恢复'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('恢复失败: restore failed');
    });
    alertSpy.mockRestore();
  });

  it('handles delete department error', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    mockInvoke.mockImplementation((_method: string, opts: { method: string }) => {
      if (opts.method === 'org.department.delete') return Promise.reject(new Error('dept delete failed'));
      return defaultResponder('', opts);
    });
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    fireEvent.click(screen.getByText('Test Corp'));
    await waitFor(() => screen.getByText('Engineering'));

    const deptItem = screen.getByText('Engineering').closest('[class*="bg-gray-50"]')!;
    const trashBtn = deptItem.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);
    fireEvent.click(screen.getByText('删除'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('删除部门失败: dept delete failed');
    });
    alertSpy.mockRestore();
  });

  it('retry button refetches data on error', async () => {
    mockInvoke.mockImplementation(() => Promise.reject(new Error('Network error')));
    renderWithQuery(<CompanyList />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    }, { timeout: 5000 });

    mockInvoke.mockImplementation(defaultResponder);
    fireEvent.click(screen.getByText('重试'));

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument();
    });
  });

  it('ConfirmDialog cancel closes dialog', async () => {
    renderWithQuery(<CompanyList />);
    await waitFor(() => screen.getByText('Test Corp'));

    const companyItem = screen.getByText('Test Corp').closest('[class*="border-b"]')!;
    const trashBtn = companyItem.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);
    expect(screen.getByText('删除确认')).toBeInTheDocument();

    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('删除确认')).not.toBeInTheDocument();
  });
});
