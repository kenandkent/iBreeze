import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './Layout';
import { useAppStore } from '../../stores/appStore';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

function renderWithQuery(ui: React.ReactElement, initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/" element={ui}>
            <Route path="companies" element={<div>公司管理内容</div>} />
            <Route path="employees" element={<div>员工管理内容</div>} />
            <Route path="session" element={<div>会话内容</div>} />
            <Route path="tasks" element={<div>任务看板内容</div>} />
            <Route path="settings" element={<div>系统信息</div>} />
            <Route path="dashboard" element={<div>概览内容</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Layout', () => {
  it('renders sidebar with iBreeze title', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('iBreeze').length).toBeGreaterThan(0);
  });

  it('renders header with page title', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />, ['/companies']);
    const titles = screen.getAllByText('公司管理');
    expect(titles.length).toBeGreaterThanOrEqual(1);
  });

  it('renders companies page', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />, ['/companies']);
    expect(screen.getAllByText('公司管理').length).toBeGreaterThan(0);
  });

  it('renders settings page', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />, ['/settings']);
    expect(screen.getByText('系统信息')).toBeInTheDocument();
  });

  it('renders tasks page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />, ['/tasks']);
    expect(screen.getAllByText('任务看板').length).toBeGreaterThan(0);
  });

  it('renders employees page', () => {
    mockInvoke.mockResolvedValue([]);
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />, ['/employees']);
    expect(screen.getAllByText('员工管理').length).toBeGreaterThan(0);
  });

  it('renders session page by default', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderWithQuery(<Layout />);
    expect(screen.getAllByText('会话').length).toBeGreaterThan(0);
  });
});
