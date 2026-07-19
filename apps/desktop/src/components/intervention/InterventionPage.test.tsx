import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InterventionPage } from './InterventionPage';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

vi.mock('../../stores/appStore', () => ({
  useAppStore: () => ({ currentCompanyId: 'c1' }),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockIntervention = (overrides: Partial<Record<string, unknown>> = {}) => ({
  intervention_id: 'i1',
  company_id: 'c1',
  reason: '异常预算',
  target_ref: 'task-1',
  status: 'pending',
  created_at: '2026-07-19T00:00:00Z',
  ...overrides,
});

const listResp = (items: unknown[], total: number) => ({ items, total });

describe('InterventionPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue(listResp([], 0));
    renderWithQuery(<InterventionPage />);
    await waitFor(() => expect(screen.getByText('暂无人工干预')).toBeInTheDocument());
  });

  it('renders intervention list', async () => {
    mockInvoke.mockResolvedValue(listResp([mockIntervention()], 1));
    renderWithQuery(<InterventionPage />);
    await waitFor(() => expect(screen.getByText('异常预算')).toBeInTheDocument());
    expect(screen.getByText('task-1')).toBeInTheDocument();
  });

  it('filters by status', async () => {
    mockInvoke.mockResolvedValue(listResp([mockIntervention()], 1));
    renderWithQuery(<InterventionPage />);
    await waitFor(() => screen.getByText('异常预算'));
    fireEvent.change(screen.getByDisplayValue('全部状态'), { target: { value: 'pending' } });
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'intervention.list',
        params: expect.stringContaining('pending'),
      }));
    });
  });

  it('paginates to next page', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string; params: string }) => {
      if (opts.method === 'intervention.list') {
        const p = JSON.parse(opts.params);
        if (p.offset === 0) return Promise.resolve(listResp([mockIntervention()], 15));
        return Promise.resolve(listResp([mockIntervention({ intervention_id: 'i2' })], 15));
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<InterventionPage />);
    await waitFor(() => screen.getByText('异常预算'));
    fireEvent.click(screen.getByText('下一页'));
    await waitFor(() => expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument());
    const calls = mockInvoke.mock.calls.filter((c) => c[1].method === 'intervention.list');
    expect(calls.some((c) => JSON.parse(c[1].params).offset === 10)).toBe(true);
  });
});
