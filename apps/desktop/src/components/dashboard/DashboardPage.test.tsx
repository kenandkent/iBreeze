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

  it('calls task and session rpcs', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string; params?: string }) => {
      switch (opts.method) {
        case 'task.list':
          return Promise.resolve([{ task_id: 'k1', company_id: 'c1', title: 'T1', description: '', status: 'in_progress', priority: 1, version: 1, created_at: '2026-07-19T00:00:00Z' }]);
        case 'session.list':
          return Promise.resolve({ threads: [{ thread_id: 's1', company_id: 'c1', user_id: 'u1', status: 'active', security_context: {}, created_at: '2026-07-19T00:00:00Z', updated_at: '2026-07-19T00:00:00Z' }], total: 1 });
        default:
          return Promise.resolve([]);
      }
    });

    renderWithQuery(<DashboardPage />);

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'task.list' }));
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({ method: 'session.list' }));
    });
  });

  it('renders card counts', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      switch (opts.method) {
        case 'task.list':
          return Promise.resolve([
            { task_id: 'k1', company_id: 'c1', title: 'T1', description: '', status: 'in_progress', priority: 1, version: 1, created_at: '2026-07-19T00:00:00Z' },
          ]);
        case 'session.list':
          return Promise.resolve({ threads: [
            { thread_id: 's1', company_id: 'c1', user_id: 'u1', status: 'active', security_context: {}, created_at: '2026-07-19T00:00:00Z', updated_at: '2026-07-19T00:00:00Z' },
          ], total: 1 });
        default:
          return Promise.resolve([]);
      }
    });

    renderWithQuery(<DashboardPage />);

    await waitFor(() => {
      const values = screen.getAllByText('1');
      expect(values.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('aggregates card counts from each rpc return value', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      switch (opts.method) {
        case 'task.list':
          return Promise.resolve([
            { task_id: 'k1', company_id: 'c1', title: 'T1', description: '', status: 'in_progress', priority: 1, version: 1, created_at: '2026-07-19T00:00:00Z' },
            { task_id: 'k2', company_id: 'c1', title: 'T2', description: '', status: 'completed', priority: 1, version: 1, created_at: '2026-07-19T00:00:00Z' },
          ]);
        case 'session.list':
          return Promise.resolve({ threads: [
            { thread_id: 's1', company_id: 'c1', user_id: 'u1', status: 'active', security_context: {}, created_at: '2026-07-19T00:00:00Z', updated_at: '2026-07-19T00:00:00Z' },
            { thread_id: 's2', company_id: 'c1', user_id: 'u2', status: 'closed', security_context: {}, created_at: '2026-07-19T00:00:00Z', updated_at: '2026-07-19T00:00:00Z' },
          ], total: 2 });
        default:
          return Promise.resolve([]);
      }
    });

    renderWithQuery(<DashboardPage />);

    await waitFor(() => {
      const ones = screen.getAllByText('1');
      expect(ones.length).toBeGreaterThanOrEqual(2);
    });
  });
});
