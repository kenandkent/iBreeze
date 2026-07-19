import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Header } from './Header';
import { useAppStore } from '../../stores/appStore';
import type { PageKey } from '../../types';

const mockRpcCall = vi.fn();
vi.mock('../../services/rpcClient', () => ({
  rpcCall: (...args: unknown[]) => mockRpcCall(...args),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockCompany = (overrides: Partial<Record<string, unknown>> = {}) => ({
  company_id: 'c1',
  name: '测试公司',
  status: 'active',
  root_department_id: 'dep1',
  version: 1,
  created_at: '2026-07-19T00:00:00Z',
  updated_at: '2026-07-19T00:00:00Z',
  ...overrides,
});

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.setState({ currentCompanyId: null, currentPage: 'companies' as PageKey });
  });

  const PAGE_TITLE_MAP: Record<string, string> = {
    companies: '公司管理',
    employees: '员工管理',
    tasks: '任务看板',
    knowledge: '知识库',
    capabilities: '能力管理',
    skills: '技能管理',
    prompts: 'Prompt 资产',
    templates: '员工模板',
    settings: '设置',
  };

  for (const [page, title] of Object.entries(PAGE_TITLE_MAP)) {
    it(`shows correct title for "${page}"`, async () => {
      mockRpcCall.mockResolvedValue([]);
      useAppStore.setState({ currentPage: page as PageKey });
      renderWithQuery(<Header />);
      expect(screen.getByText(title)).toBeInTheDocument();
    });
  }

  it('shows refresh button when onRefresh is provided', async () => {
    mockRpcCall.mockResolvedValue([]);
    const onRefresh = vi.fn();
    renderWithQuery(<Header onRefresh={onRefresh} />);
    expect(await screen.findByText('刷新')).toBeInTheDocument();
  });

  it('hides refresh button when no onRefresh', async () => {
    mockRpcCall.mockResolvedValue([]);
    renderWithQuery(<Header />);
    await waitFor(() => expect(mockRpcCall).toHaveBeenCalled());
    expect(screen.queryByText('刷新')).not.toBeInTheDocument();
  });

  it('calls onRefresh on click', async () => {
    mockRpcCall.mockResolvedValue([]);
    const onRefresh = vi.fn();
    renderWithQuery(<Header onRefresh={onRefresh} />);
    fireEvent.click(await screen.findByText('刷新'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  describe('company selector', () => {
    it('shows company selector when companies exist', async () => {
      mockRpcCall.mockResolvedValue([mockCompany()]);
      renderWithQuery(<Header />);
      await waitFor(() => expect(screen.getByDisplayValue('测试公司')).toBeInTheDocument());
    });

    it('auto-selects first active company when none selected', async () => {
      mockRpcCall.mockResolvedValue([mockCompany()]);
      renderWithQuery(<Header />);
      await waitFor(() => {
        const state = useAppStore.getState();
        expect(state.currentCompanyId).toBe('c1');
      });
    });

    it('does not auto-select when companies already selected', async () => {
      useAppStore.setState({ currentCompanyId: 'existing' });
      mockRpcCall.mockResolvedValue([mockCompany({ company_id: 'c2', name: '其他公司' })]);
      renderWithQuery(<Header />);
      await waitFor(() => expect(mockRpcCall).toHaveBeenCalled());
      expect(useAppStore.getState().currentCompanyId).toBe('existing');
    });

    it('switches company on select change', async () => {
      mockRpcCall.mockResolvedValue([
        mockCompany(),
        mockCompany({ company_id: 'c2', name: '第二公司' }),
      ]);
      renderWithQuery(<Header />);
      await waitFor(() => expect(screen.getByDisplayValue('测试公司')).toBeInTheDocument());
      fireEvent.change(screen.getByDisplayValue('测试公司'), { target: { value: 'c2' } });
      expect(useAppStore.getState().currentCompanyId).toBe('c2');
    });

    it('filters out non-active companies from selector', async () => {
      mockRpcCall.mockResolvedValue([
        mockCompany(),
        mockCompany({ company_id: 'c2', name: '已解散', status: 'dissolved' }),
      ]);
      renderWithQuery(<Header />);
      await waitFor(() => expect(screen.getByDisplayValue('测试公司')).toBeInTheDocument());
      expect(screen.queryByDisplayValue('已解散')).not.toBeInTheDocument();
    });

    it('hides selector when no active companies', async () => {
      mockRpcCall.mockResolvedValue([]);
      renderWithQuery(<Header />);
      await waitFor(() => expect(mockRpcCall).toHaveBeenCalled());
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });
  });
});
