import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuditPage } from './AuditPage';

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

const mockAudit = (overrides: Partial<Record<string, unknown>> = {}) => ({
  audit_id: 'a1',
  audit_type: 'acl',
  company_id: 'c1',
  action: 'grant',
  resource: 'doc-1',
  result: 'success',
  created_at: '2026-07-19T00:00:00Z',
  ...overrides,
});

const listResp = (items: unknown[], total: number) => ({ items, total });

describe('AuditPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue(listResp([], 0));
    renderWithQuery(<AuditPage />);
    await waitFor(() => expect(screen.getByText('暂无审计记录')).toBeInTheDocument());
  });

  it('renders audit list', async () => {
    mockInvoke.mockResolvedValue(listResp([mockAudit()], 1));
    renderWithQuery(<AuditPage />);
    await waitFor(() => expect(screen.getByText('grant')).toBeInTheDocument());
    expect(screen.getByText('doc-1')).toBeInTheDocument();
  });

  it('switches audit_type and queries with different type', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string; params: string }) => {
      if (opts.method === 'audit.query') {
        const p = JSON.parse(opts.params);
        if (p.audit_type === 'acl') return Promise.resolve(listResp([mockAudit({ audit_type: 'acl' })], 1));
        return Promise.resolve(listResp([mockAudit({ audit_type: 'org', action: 'org_action' })], 1));
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<AuditPage />);
    await waitFor(() => screen.getByText('grant'));
    fireEvent.click(screen.getByText('组织'));
    await waitFor(() => expect(screen.getByText('org_action')).toBeInTheDocument());
    const calls = mockInvoke.mock.calls.filter((c) => c[1].method === 'audit.query');
    expect(calls.some((c) => JSON.parse(c[1].params).audit_type === 'org')).toBe(true);
  });

  it('paginates', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string; params: string }) => {
      if (opts.method === 'audit.query') {
        const p = JSON.parse(opts.params);
        if (p.offset === 0) return Promise.resolve(listResp([mockAudit()], 15));
        return Promise.resolve(listResp([mockAudit({ audit_id: 'a2' })], 15));
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<AuditPage />);
    await waitFor(() => screen.getByText('grant'));
    fireEvent.click(screen.getByText('下一页'));
    await waitFor(() => expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument());
  });
});
