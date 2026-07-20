import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DashboardPage } from './DashboardPage';
import { useAppStore } from '../../stores/appStore';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.setState({ currentCompanyId: 'c1' });
  });

  it('shows prompt when no company selected', () => {
    useAppStore.setState({ currentCompanyId: null });
    renderWithQuery(<DashboardPage />);
    expect(screen.getByText('请先在上方选择公司后再查看概览。')).toBeInTheDocument();
  });

  it('calls all aggregation rpcs', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string; params?: string }) => {
      switch (opts.method) {
        case 'company.list':
          return Promise.resolve([{ company_id: 'c1', name: 'C1', status: 'active', created_at: '2026-07-19T00:00:00Z' }]);
        case 'employee.list':
          return Promise.resolve([{ employee_id: 'e1', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E1', role_name: 'r', employee_type: 'ft', status: 'active' }]);
        case 'task.list':
          return Promise.resolve([{ task_id: 'k1', company_id: 'c1', title: 'T1', description: '', status: 'in_progress', priority: 1, version: 1, created_at: '2026-07-19T00:00:00Z' }]);
        case 'knowledge.list':
          return Promise.resolve([{ document_id: 'd1', company_id: 'c1', title: 'D1', source_category: 'custom', status: 'active' }]);
        case 'backend.list':
          return Promise.resolve([{ backend_id: 'b1', name: 'B1', type: 'openai', status: 'active', health: 'healthy', capacity: 100, company_id: 'c1' }]);
        case 'session.list':
          return Promise.resolve([{ thread_id: 's1', company_id: 'c1', user_id: 'u1', status: 'active', security_context: {}, created_at: '2026-07-19T00:00:00Z', updated_at: '2026-07-19T00:00:00Z' }]);
        case 'intervention.list':
          return Promise.resolve({ items: [], total: 3 });
        default:
          return Promise.resolve([]);
      }
    });

    renderWithQuery(<DashboardPage />);

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'company.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'employee.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'task.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'knowledge.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'backend.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'session.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'intervention.list' }));
    });
  });

  it('renders card counts', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      switch (opts.method) {
        case 'company.list':
          return Promise.resolve([
            { company_id: 'c1', name: 'C1', status: 'active', created_at: '2026-07-19T00:00:00Z' },
            { company_id: 'c2', name: 'C2', status: 'active', created_at: '2026-07-19T00:00:00Z' },
          ]);
        case 'employee.list':
          return Promise.resolve([
            { employee_id: 'e1', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E1', role_name: 'r', employee_type: 'ft', status: 'active' },
            { employee_id: 'e2', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E2', role_name: 'r', employee_type: 'ft', status: 'active' },
            { employee_id: 'e3', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E3', role_name: 'r', employee_type: 'ft', status: 'active' },
          ]);
        case 'task.list':
          return Promise.resolve([{ task_id: 'k1', company_id: 'c1', title: 'T1', description: '', status: 'in_progress', priority: 1, version: 1, created_at: '2026-07-19T00:00:00Z' }]);
        case 'knowledge.list':
          return Promise.resolve([
            { document_id: 'd1', company_id: 'c1', title: 'D1', source_category: 'custom', status: 'active' },
            { document_id: 'd2', company_id: 'c1', title: 'D2', source_category: 'custom', status: 'active' },
          ]);
        case 'backend.list':
          return Promise.resolve([
            { backend_id: 'b1', name: 'B1', type: 'openai', status: 'active', health: 'healthy', capacity: 100, company_id: 'c1' },
            { backend_id: 'b2', name: 'B2', type: 'openai', status: 'inactive', health: 'healthy', capacity: 100, company_id: 'c1' },
          ]);
        case 'session.list':
          return Promise.resolve([]);
        case 'intervention.list':
          return Promise.resolve({ items: [], total: 3 });
        default:
          return Promise.resolve([]);
      }
    });

    renderWithQuery(<DashboardPage />);

    const taskLabel = screen.getAllByText('进行中任务').find(
      (el) => el.className.includes('text-xs')
    )!;
    await waitFor(() => expect(taskLabel.closest('.bg-white')!).toHaveTextContent('1'));
    expect(screen.getByText('员工数')).toBeInTheDocument();
    expect(screen.getByText('知识文档数')).toBeInTheDocument();
    expect(screen.getByText('活跃 Backend')).toBeInTheDocument();
    const interventionCard = screen.getByText('待处理干预').closest('div')!.parentElement!;
    expect(interventionCard).toHaveTextContent('3');
  });

  it('aggregates card counts from each rpc return value', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      switch (opts.method) {
        // 公司数 = company.list 长度 (2)
        case 'company.list':
          return Promise.resolve([
            { company_id: 'c1', name: 'C1', status: 'active', created_at: '2026-07-19T00:00:00Z' },
            { company_id: 'c2', name: 'C2', status: 'active', created_at: '2026-07-19T00:00:00Z' },
          ]);
        // 员工数 = employee.list 长度 (3)
        case 'employee.list':
          return Promise.resolve([
            { employee_id: 'e1', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E1', role_name: 'r', employee_type: 'ft', status: 'active' },
            { employee_id: 'e2', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E2', role_name: 'r', employee_type: 'ft', status: 'active' },
            { employee_id: 'e3', company_id: 'c1', department_id: 'd1', template_id: 't1', name: 'E3', role_name: 'r', employee_type: 'ft', status: 'active' },
          ]);
        case 'task.list':
          return Promise.resolve([]);
        // 知识文档数 = knowledge.list 长度 (2)
        case 'knowledge.list':
          return Promise.resolve([
            { document_id: 'd1', company_id: 'c1', title: 'D1', source_category: 'custom', status: 'active' },
            { document_id: 'd2', company_id: 'c1', title: 'D2', source_category: 'custom', status: 'active' },
          ]);
        // 活跃 Backend = backend.list 中 status==='active' 的数量 (1)
        case 'backend.list':
          return Promise.resolve([
            { backend_id: 'b1', name: 'B1', type: 'openai', status: 'active', health: 'healthy', capacity: 100, company_id: 'c1' },
            { backend_id: 'b2', name: 'B2', type: 'openai', status: 'inactive', health: 'healthy', capacity: 100, company_id: 'c1' },
          ]);
        case 'session.list':
          return Promise.resolve([]);
        // 待处理干预 = intervention.list(pending) 的 total (5)
        case 'intervention.list':
          return Promise.resolve({ items: [], total: 5 });
        default:
          return Promise.resolve([]);
      }
    });

    renderWithQuery(<DashboardPage />);

    const cardValue = (label: string) => screen.getByText(label).closest('.bg-white')!;

    await waitFor(() => expect(cardValue('公司数')).toHaveTextContent('2'));
    expect(cardValue('员工数')).toHaveTextContent('3');
    expect(cardValue('知识文档数')).toHaveTextContent('2');
    expect(cardValue('活跃 Backend')).toHaveTextContent('1');
    expect(cardValue('待处理干预')).toHaveTextContent('5');

    // 断言 intervention.list 以 pending 状态查询
    expect(mockInvoke).toHaveBeenCalledWith(
      'sys_rpc_call',
      expect.objectContaining({ method: 'intervention.list', params: expect.stringContaining('"status":"pending"') }),
    );
  });
});
