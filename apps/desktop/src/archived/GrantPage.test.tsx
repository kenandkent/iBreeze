import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GrantPage } from './GrantPage';

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

const mockGrant = (overrides: Partial<Record<string, unknown>> = {}) => ({
  grant_id: 'g1',
  company_id: 'c1',
  target_type: 'department',
  target_ref: 'd1',
  permission: 'read',
  expires_at: '2026-07-19T00:00:00Z',
  status: 'active',
  created_at: '2026-07-19T00:00:00Z',
  ...overrides,
});

describe('GrantPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue({ grants: [], total: 0 });
    renderWithQuery(<GrantPage />);
    await waitFor(() => expect(screen.getByText('暂无授权')).toBeInTheDocument());
  });

  it('renders grant list', async () => {
    mockInvoke.mockResolvedValue({ grants: [mockGrant()], total: 1 });
    renderWithQuery(<GrantPage />);
    await waitFor(() => expect(screen.getByText('department')).toBeInTheDocument());
    expect(screen.getByText('d1')).toBeInTheDocument();
  });

  it('creates grant via org.grant.create', async () => {
    mockInvoke.mockResolvedValue({ grants: [], total: 0 });
    renderWithQuery(<GrantPage />);
    await waitFor(() => screen.getByText('暂无授权'));
    fireEvent.click(screen.getByText('新建授权'));
    fireEvent.change(screen.getByPlaceholderText('请输入部门或任务 ID'), { target: { value: 'd1' } });
    fireEvent.change(screen.getByPlaceholderText('请输入权限标识'), { target: { value: 'read' } });
    fireEvent.click(screen.getByText('确认创建'));
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'org.grant.create',
      }));
    });
  });

  it('revokes grant via org.grant.revoke', async () => {
    mockInvoke.mockResolvedValue({ grants: [mockGrant()], total: 1 });
    renderWithQuery(<GrantPage />);
    await waitFor(() => screen.getByText('department'));
    fireEvent.click(screen.getByText('撤销'));
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'org.grant.revoke',
      }));
    });
  });
});
