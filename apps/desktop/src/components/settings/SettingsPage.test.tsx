import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SettingsPage } from './SettingsPage';

const mockRpcCall = vi.fn();
vi.mock('../../services/rpcClient', () => ({
  rpcCall: (...args: unknown[]) => mockRpcCall(...args),
}));

vi.mock('../../stores/appStore', () => ({
  useAppStore: (selector: (s: { currentCompanyId: string | null }) => unknown) =>
    selector({ currentCompanyId: 'c1' }),
}));

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders 设置 title', () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    expect(screen.getByText('设置')).toBeInTheDocument();
  });

  it('shows 系统信息 section', () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    expect(screen.getByText('系统信息')).toBeInTheDocument();
  });

  it('shows 版本 info', () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    expect(screen.getByText('版本')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
  });

  it('shows 关于 section with description', () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    expect(screen.getByText('关于')).toBeInTheDocument();
    expect(screen.getByText(/iBreeze 是一个本地 AI 组织运行平台/)).toBeInTheDocument();
  });

  it('shows 平台 info', () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    expect(screen.getByText('平台')).toBeInTheDocument();
    expect(screen.getByText('macOS Apple Silicon')).toBeInTheDocument();
  });

  it('shows 正常 status when sys.health succeeds', async () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText('正常')).toBeInTheDocument();
    });
  });

  it('shows 未连接 when sys.health fails', async () => {
    mockRpcCall.mockRejectedValue(new Error('not running'));
    renderWithQuery(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText('未连接')).toBeInTheDocument();
    });
  });

  it('shows 检查中... initially before health resolves', () => {
    mockRpcCall.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<SettingsPage />);
    expect(screen.getByText('检查中...')).toBeInTheDocument();
  });

  it('calls rpcCall with sys.health method', () => {
    mockRpcCall.mockResolvedValue({ status: 'healthy' });
    renderWithQuery(<SettingsPage />);
    expect(mockRpcCall).toHaveBeenCalledWith('sys.health');
  });

  it('renders policy sections for current company', async () => {
    mockRpcCall.mockImplementation((method: string) => {
      if (method === 'sys.health') return Promise.resolve({ status: 'healthy' });
      if (method.endsWith('.get')) return Promise.resolve({ version: 1, exists: true });
      return Promise.resolve({});
    });
    renderWithQuery(<SettingsPage />);
    expect(await screen.findByText('公司设置')).toBeInTheDocument();
    expect(await screen.findByText('知识策略')).toBeInTheDocument();
  });
});
