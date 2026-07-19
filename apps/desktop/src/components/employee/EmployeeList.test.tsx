import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EmployeeList } from './EmployeeList';

const mockRpcCall = vi.fn();
vi.mock('../../services/rpcClient', () => ({
  rpcCall: (...args: unknown[]) => mockRpcCall(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockEmployee = (overrides: Partial<Record<string, unknown>> = {}) => ({
  employee_id: 'e1',
  name: 'Alice',
  role_name: 'Engineer',
  company_id: 'c1',
  department_id: 'd1',
  status: 'active',
  created_at: '2024-01-01',
  ...overrides,
});

const mockCompany = (overrides: Partial<Record<string, unknown>> = {}) => ({
  company_id: 'c1',
  name: 'Test Corp',
  status: 'active',
  ...overrides,
});

const mockDept = (overrides: Partial<Record<string, unknown>> = {}) => ({
  department_id: 'd1',
  company_id: 'c1',
  name: 'Engineering',
  status: 'active',
  ...overrides,
});

function defaultResponder(method: string) {
  switch (method) {
    case 'org.employee.list':
      return Promise.resolve([mockEmployee()]);
    case 'org.company.list':
      return Promise.resolve([mockCompany()]);
    case 'org.department.list':
      return Promise.resolve([mockDept()]);
    default:
      return Promise.resolve({ ok: true });
  }
}

describe('EmployeeList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRpcCall.mockImplementation(defaultResponder);
  });

  it('renders loading state', () => {
    mockRpcCall.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<EmployeeList />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders error state', async () => {
    mockRpcCall.mockImplementation(() => Promise.reject(new Error('fail')));
    renderWithQuery(<EmployeeList />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders empty state', async () => {
    mockRpcCall.mockImplementation(() => Promise.resolve([]));
    renderWithQuery(<EmployeeList />);
    await waitFor(() => {
      expect(screen.getByText('暂无员工数据')).toBeInTheDocument();
    });
  });

  it('renders employees', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument();
      expect(screen.getByText('Engineer')).toBeInTheDocument();
    });
  });

  it('shows table headers', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => {
      expect(screen.getByText('姓名')).toBeInTheDocument();
      expect(screen.getByText('角色')).toBeInTheDocument();
      expect(screen.getByText('状态')).toBeInTheDocument();
      expect(screen.getByText('操作')).toBeInTheDocument();
    });
  });

  it('opens create modal', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));
    expect(screen.getByText('新建员工', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入姓名')).toBeInTheDocument();
  });

  it('creates employee', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));

    fireEvent.change(screen.getByPlaceholderText('请输入姓名'), { target: { value: 'Bob' } });
    fireEvent.change(screen.getByPlaceholderText('如：开发工程师、项目经理'), { target: { value: 'Manager' } });

    expect(screen.getByText('确认')).toBeDisabled();
  });

  it('department select is disabled when no company selected', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));

    const deptSelect = screen.getByText('请选择部门').closest('select')!;
    expect(deptSelect).toBeDisabled();
  });

  it('cancel closes modal', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByPlaceholderText('请输入姓名')).not.toBeInTheDocument();
  });

  it('submit button is disabled when required fields empty', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));
    expect(screen.getByText('确认')).toBeDisabled();
  });

  it('opens edit modal', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('Alice'));

    const row = screen.getByText('Alice').closest('tr')!;
    const pencilBtn = row.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);

    expect(screen.getByText('编辑员工')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Alice')).toBeInTheDocument();
  });

  it('updates employee', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('Alice'));

    const row = screen.getByText('Alice').closest('tr')!;
    const pencilBtn = row.querySelector('.lucide-pencil')?.closest('button');
    fireEvent.click(pencilBtn!);

    await waitFor(() => expect(screen.getByDisplayValue('Alice')).toBeInTheDocument());

    fireEvent.change(screen.getByDisplayValue('Alice'), { target: { value: 'Charlie' } });
    await waitFor(() => expect(screen.getByDisplayValue('Charlie')).toBeInTheDocument());

    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const call = mockRpcCall.mock.calls.find(
        (c: unknown[]) => c[0] === 'org.employee.update',
      );
      expect(call).toBeTruthy();
    });
  });

  it('opens delete confirm', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('Alice'));

    const row = screen.getByText('Alice').closest('tr')!;
    const trashBtn = row.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);

    expect(screen.getByText('删除确认')).toBeInTheDocument();
    expect(screen.getByText(/确定删除员工「Alice」/)).toBeInTheDocument();
  });

  it('deletes employee on confirm', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('Alice'));

    const row = screen.getByText('Alice').closest('tr')!;
    const trashBtn = row.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);
    fireEvent.click(screen.getByText('删除'));

    await waitFor(() => {
      const call = mockRpcCall.mock.calls.find(
        (c: unknown[]) => c[0] === 'org.employee.delete',
      );
      expect(call).toBeTruthy();
    });
  });

  it('cancel delete closes confirm', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('Alice'));

    const row = screen.getByText('Alice').closest('tr')!;
    const trashBtn = row.querySelector('.lucide-trash2')?.closest('button');
    fireEvent.click(trashBtn!);
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('删除确认')).not.toBeInTheDocument();
  });

  it('creates employee with all required fields', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));

    const companySelect = screen.getByDisplayValue('请选择公司');
    fireEvent.change(companySelect, { target: { value: 'c1' } });

    fireEvent.change(screen.getByPlaceholderText('请输入姓名'), { target: { value: 'Bob' } });
    fireEvent.change(screen.getByPlaceholderText('如：开发工程师、项目经理'), { target: { value: 'Manager' } });

    const submitBtn = screen.getByText('确认');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      const call = mockRpcCall.mock.calls.find(
        (c: unknown[]) => c[0] === 'org.employee.create',
      );
      expect(call).toBeTruthy();
    });
  });

  it('retry button refetches on error', async () => {
    mockRpcCall.mockImplementation(() => Promise.reject(new Error('fail')));
    renderWithQuery(<EmployeeList />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    }, { timeout: 5000 });

    mockRpcCall.mockImplementation(defaultResponder);
    fireEvent.click(screen.getByText('重试'));

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
  });

  it('selecting company triggers department query', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));

    const companySelect = screen.getByDisplayValue('请选择公司');
    fireEvent.change(companySelect, { target: { value: 'c1' } });

    await waitFor(() => {
      const deptCall = mockRpcCall.mock.calls.find(
        (c: unknown[]) => c[0] === 'org.department.list',
      );
      expect(deptCall).toBeTruthy();
    });
  });

  it('resetting company clears department_id', async () => {
    renderWithQuery(<EmployeeList />);
    await waitFor(() => screen.getByText('员工列表'));

    fireEvent.click(screen.getByText('新建员工'));

    const companySelect = screen.getByDisplayValue('请选择公司');
    fireEvent.change(companySelect, { target: { value: 'c1' } });
    fireEvent.change(companySelect, { target: { value: '' } });

    const deptSelect = screen.getByDisplayValue('请选择部门') as HTMLSelectElement;
    expect(deptSelect).toBeDisabled();
  });
});
