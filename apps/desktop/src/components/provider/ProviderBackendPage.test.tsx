import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProviderBackendPage } from './ProviderBackendPage';

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

const mockBackend = (overrides: Partial<Record<string, unknown>> = {}) => ({
  backend_id: 'b1',
  name: 'Backend-A',
  type: 'openai',
  status: 'active',
  health: 'healthy',
  capacity: 100,
  company_id: 'c1',
  ...overrides,
});

const mockProvider = (overrides: Partial<Record<string, unknown>> = {}) => ({
  provider_id: 'p1',
  name: 'Provider-A',
  type: 'llm',
  status: 'active',
  company_id: 'c1',
  ...overrides,
});

const mockModel = (overrides: Partial<Record<string, unknown>> = {}) => ({
  model_id: 'm1',
  provider_id: 'p1',
  name: 'gpt-4o',
  company_id: 'c1',
  ...overrides,
});

describe('ProviderBackendPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders backend list', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([mockBackend()]);
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => expect(screen.getByText('Backend-A')).toBeInTheDocument());
    expect(screen.getByText('openai')).toBeInTheDocument();
  });

  it('probe button calls backend.probe', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([mockBackend()]);
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('Backend-A'));
    fireEvent.click(screen.getByText('探测'));
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'backend.probe',
      }));
    });
  });

  it('renders provider models', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([mockBackend()]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [mockProvider()], tier_mapping: {} });
      if (opts.method === 'provider.model.list') return Promise.resolve({ items: [mockModel()] });
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('Provider-A'));
    fireEvent.click(screen.getByText('Provider-A').closest('tr')!);
    await waitFor(() => expect(screen.getByText('gpt-4o')).toBeInTheDocument());
  });

  it('creates provider via provider.create', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [], tier_mapping: {} });
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('新建 Provider'));

    fireEvent.click(screen.getByText('新建 Provider'));
    fireEvent.change(screen.getByPlaceholderText('如：opencode'), { target: { value: 'opencode' } });
    fireEvent.change(screen.getByPlaceholderText('如：openai / agent'), { target: { value: 'agent' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'provider.create',
      }));
      const call = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.create');
      const params = JSON.parse((call![1] as Record<string, string>).params);
      expect(params.name).toBe('opencode');
      expect(params.provider_type).toBe('agent');
    });
  });

  it('creates backend via backend.create', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [], tier_mapping: {} });
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('新建 Backend'));

    fireEvent.click(screen.getByText('新建 Backend'));
    fireEvent.change(screen.getByPlaceholderText('如：opencode-local'), { target: { value: 'opencode-local' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
        method: 'backend.create',
      }));
      const call = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'backend.create');
      const params = JSON.parse((call![1] as Record<string, string>).params);
      expect(params.name).toBe('opencode-local');
      expect(params.company_id).toBe('c1');
    });
  });
});
