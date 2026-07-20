import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SessionPage } from './SessionPage';
import { useAppStore } from '../../stores/appStore';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockThread = (overrides: Partial<Record<string, unknown>> = {}) => ({
  thread_id: 't1',
  company_id: 'c1',
  user_id: 'u1',
  status: 'active',
  security_context: { level: 'standard' },
  created_at: '2026-07-19T00:00:00Z',
  updated_at: '2026-07-19T00:00:00Z',
  ...overrides,
});

describe('SessionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.setState({ currentCompanyId: 'c1' });
  });

  it('shows prompt when no company selected', () => {
    useAppStore.setState({ currentCompanyId: null });
    renderWithQuery(<SessionPage />);
    expect(screen.getByText('请先在上方选择公司后再查看会话。')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    mockInvoke.mockResolvedValue({ threads: [], total: 0 });
    renderWithQuery(<SessionPage />);
    await waitFor(() => expect(screen.getByText('暂无会话')).toBeInTheDocument());
  });

  it('renders thread list', async () => {
    mockInvoke.mockResolvedValue({ threads: [mockThread()], total: 1 });
    renderWithQuery(<SessionPage />);
    await waitFor(() => expect(screen.getByText('active')).toBeInTheDocument());
  });

  it('shows transcript on thread select', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'session.list') return Promise.resolve({ threads: [mockThread()], total: 1 });
      if (opts.method === 'session.transcript.get')
        return Promise.resolve({ thread_id: 't1', transcript: [{ message_id: 'm1', role: 'user', content: '你好', created_at: '2026-07-19T00:00:00Z' }], total: 1 });
      return Promise.resolve({ threads: [], total: 0 });
    });
    renderWithQuery(<SessionPage />);
    await waitFor(() => screen.getByText('active'));
    fireEvent.click(screen.getByText('active').closest('tr')!);
    await waitFor(() => expect(screen.getByText('你好')).toBeInTheDocument());
  });

  it('sends message via session.sendMessage', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'session.list') return Promise.resolve({ threads: [mockThread()], total: 1 });
      if (opts.method === 'session.transcript.get') return Promise.resolve({ thread_id: 't1', transcript: [], total: 0 });
      return Promise.resolve({});
    });
    renderWithQuery(<SessionPage />);
    await waitFor(() => screen.getByText('active'));
    fireEvent.click(screen.getByText('active').closest('tr')!);
    const input = await screen.findByPlaceholderText('输入消息...');
    fireEvent.change(input, { target: { value: '新消息' } });
    fireEvent.click(screen.getByText('发送'));
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'session.sendMessage',
      }));
    });
  });
});
