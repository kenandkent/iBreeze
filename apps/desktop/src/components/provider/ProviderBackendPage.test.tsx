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

  it('creates api provider with vendor + key + fetched model and sets credential', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [], tier_mapping: {} });
      if (opts.method === 'provider.agent.list') return Promise.resolve({ agents: [] });
      if (opts.method === 'provider.models.fetch') {
        return Promise.resolve({ models: [{ model: 'gpt-5.1-codex', display_name: 'GPT-5.1 Codex' }], source: 'live' });
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('新建 Provider'));

    fireEvent.click(screen.getByText('新建 Provider'));
    fireEvent.change(screen.getByPlaceholderText('如：opencode'), { target: { value: 'MyOpenAI' } });
    fireEvent.change(screen.getByDisplayValue('OpenAI'), { target: { value: 'openai' } });
    fireEvent.change(screen.getByPlaceholderText('API Key（用于实时查询可用模型）'), { target: { value: 'sk-xxx' } });
    fireEvent.change(screen.getByPlaceholderText('如：https://api.openai.com/v1'), { target: { value: 'https://api.openai.com/v1' } });
    fireEvent.click(screen.getByText('查询可用模型'));
    await waitFor(() => screen.getByRole('option', { name: 'GPT-5.1 Codex' }));
    const modelSelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    fireEvent.change(modelSelect, { target: { value: 'gpt-5.1-codex' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const createCall = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.create');
      expect(createCall).toBeTruthy();
      const cp = JSON.parse((createCall![1] as Record<string, string>).params);
      expect(cp.name).toBe('MyOpenAI');
      expect(cp.provider_type).toBe('api');
      expect(cp.config.api_vendor).toBe('openai');
      expect(cp.config.base_url).toBe('https://api.openai.com/v1');

      const fetchCall = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.models.fetch');
      expect(fetchCall).toBeTruthy();

      const credCall = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.credential.set');
      expect(credCall).toBeTruthy();
      const credP = JSON.parse((credCall![1] as Record<string, string>).params);
      expect(credP.credential.api_key).toBe('sk-xxx');
    });
  });

  it('api provider falls back to built-in models when fetch fails', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [], tier_mapping: {} });
      if (opts.method === 'provider.agent.list') return Promise.resolve({ agents: [] });
      if (opts.method === 'provider.models.fetch') {
        return Promise.resolve({ models: [{ model: 'gpt-5.1-codex', display_name: 'GPT-5.1 Codex' }], source: 'fallback', error_message: '401' });
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('新建 Provider'));

    fireEvent.click(screen.getByText('新建 Provider'));
    fireEvent.change(screen.getByPlaceholderText('如：opencode'), { target: { value: 'MyOpenAI' } });
    fireEvent.change(screen.getByPlaceholderText('API Key（用于实时查询可用模型）'), { target: { value: 'bad' } });
    fireEvent.click(screen.getByText('查询可用模型'));
    await waitFor(() => screen.getByText(/查询失败/));
    const modelSelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    fireEvent.change(modelSelect, { target: { value: 'gpt-5.1-codex' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const createCall = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.create');
      expect(createCall).toBeTruthy();
    });
  });

  it('creates cli provider with agent + model', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [], tier_mapping: {} });
      if (opts.method === 'provider.agent.list') {
        return Promise.resolve({
          agents: [
            { agent_id: 'opencode', display_name: 'OpenCode', models: [{ model: 'anthropic/claude-sonnet-4', display_name: 'Claude Sonnet 4' }] },
          ],
        });
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('新建 Provider'));

    fireEvent.click(screen.getByText('新建 Provider'));
    fireEvent.change(screen.getByPlaceholderText('如：opencode'), { target: { value: 'opencode' } });
    fireEvent.click(screen.getByText('调用 Agent 形式'));
    await waitFor(() => screen.getByText('OpenCode'));
    fireEvent.change(screen.getByDisplayValue('请选择 Agent'), { target: { value: 'opencode' } });
    fireEvent.change(screen.getByDisplayValue('请选择模型'), { target: { value: 'anthropic/claude-sonnet-4' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const createCall = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.create');
      expect(createCall).toBeTruthy();
      const cp = JSON.parse((createCall![1] as Record<string, string>).params);
      expect(cp.provider_type).toBe('cli');
      expect(cp.config.agent).toBe('opencode');
      expect(cp.config.model).toBe('anthropic/claude-sonnet-4');
    });
  });

  it('cli provider supports custom model input', async () => {
    mockInvoke.mockImplementation((_m: string, opts: { method: string }) => {
      if (opts.method === 'backend.list') return Promise.resolve([]);
      if (opts.method === 'provider.list') return Promise.resolve({ items: [], tier_mapping: {} });
      if (opts.method === 'provider.agent.list') {
        return Promise.resolve({
          agents: [
            { agent_id: 'opencode', display_name: 'OpenCode', models: [{ model: 'anthropic/claude-sonnet-4', display_name: 'Claude Sonnet 4' }] },
          ],
        });
      }
      return Promise.resolve([]);
    });
    renderWithQuery(<ProviderBackendPage />);
    await waitFor(() => screen.getByText('新建 Provider'));

    fireEvent.click(screen.getByText('新建 Provider'));
    fireEvent.change(screen.getByPlaceholderText('如：opencode'), { target: { value: 'opencode' } });
    fireEvent.click(screen.getByText('调用 Agent 形式'));
    await waitFor(() => screen.getByText('OpenCode'));
    fireEvent.change(screen.getByDisplayValue('请选择 Agent'), { target: { value: 'opencode' } });
    fireEvent.change(screen.getByDisplayValue('请选择模型'), { target: { value: '__custom__' } });
    fireEvent.change(screen.getByPlaceholderText('手动输入模型名'), { target: { value: 'my-custom-model' } });
    fireEvent.click(screen.getByText('确认'));

    await waitFor(() => {
      const createCall = mockInvoke.mock.calls.find((c: unknown[]) => c[0] === 'sys_rpc_call' && (c[1] as Record<string, unknown>).method === 'provider.create');
      const cp = JSON.parse((createCall![1] as Record<string, string>).params);
      expect(cp.config.model).toBe('my-custom-model');
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
