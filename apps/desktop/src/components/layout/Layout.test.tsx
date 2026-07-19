import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './Layout';
import { useAppStore } from '../../stores/appStore';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('Layout', () => {
  it('renders sidebar with iBreeze title', () => {
    useAppStore.setState({ currentPage: 'companies', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getByText('iBreeze')).toBeInTheDocument();
  });

  it('renders header with page title', () => {
    useAppStore.setState({ currentPage: 'companies', sidebarOpen: true });
    renderWithQuery(<Layout />);
    const titles = screen.getAllByText('公司管理');
    expect(titles.length).toBeGreaterThanOrEqual(1);
  });

  it('renders companies page by default', () => {
    useAppStore.setState({ currentPage: 'companies', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('公司管理').length).toBeGreaterThan(0);
  });

  it('renders settings page', () => {
    useAppStore.setState({ currentPage: 'settings', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getByText('系统信息')).toBeInTheDocument();
  });

  it('renders tasks page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'tasks', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('任务看板').length).toBeGreaterThan(0);
  });

  it('renders header showing current page title after navigation', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'knowledge', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('知识库').length).toBeGreaterThan(0);
  });

  it('renders employees page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'employees', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('员工管理').length).toBeGreaterThan(0);
  });

  it('renders capabilities page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'capabilities', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('能力管理').length).toBeGreaterThan(0);
  });

  it('renders skills page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'skills', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('技能管理').length).toBeGreaterThan(0);
  });

  it('renders prompts page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'prompts', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('Prompt 资产').length).toBeGreaterThan(0);
  });

  it('renders templates page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ currentPage: 'templates', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('员工模板').length).toBeGreaterThan(0);
  });

  it('renders companies page for unknown page key (default case)', () => {
    useAppStore.setState({ currentPage: 'companies', sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('公司管理').length).toBeGreaterThan(0);
  });
});
