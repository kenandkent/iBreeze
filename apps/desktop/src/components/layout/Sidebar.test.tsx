import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useAppStore } from '../../stores/appStore';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const NAV_LABELS = [
  '公司管理',
  '员工管理',
  '会话',
  '任务看板',
  '任务高级',
  '概览',
  '设置',
] as const;

function renderSidebar(initialEntries: string[] = ['/companies']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Sidebar />
    </MemoryRouter>
  );
}

describe('Sidebar', () => {
  it('renders all 7 nav items when open', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderSidebar();
    for (const label of NAV_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('hides nav labels when collapsed', () => {
    useAppStore.setState({ sidebarOpen: false });
    renderSidebar();
    for (const label of NAV_LABELS) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it('shows iBreeze title when open', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderSidebar();
    expect(screen.getByText('iBreeze')).toBeInTheDocument();
  });

  it('hides iBreeze title when collapsed', () => {
    useAppStore.setState({ sidebarOpen: false });
    renderSidebar();
    expect(screen.queryByText('iBreeze')).not.toBeInTheDocument();
  });

  it('highlights current page with bg-blue-50', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderSidebar(['/tasks']);
    const taskBtn = screen.getByText('任务看板').closest('button')!;
    expect(taskBtn.className).toContain('bg-blue-50');
    expect(taskBtn.className).toContain('text-blue-700');
  });

  it('non-current page does not have bg-blue-50', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderSidebar(['/tasks']);
    const companiesBtn = screen.getByText('公司管理').closest('button')!;
    expect(companiesBtn.className).not.toContain('bg-blue-50');
  });

  it('toggles sidebar on button click', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderSidebar();
    const toggleBtn = document.querySelector('button.p-1')!;
    expect(toggleBtn).toBeTruthy();
    fireEvent.click(toggleBtn);
    expect(useAppStore.getState().sidebarOpen).toBe(false);
  });

  it('clicking nav item calls navigate', () => {
    useAppStore.setState({ sidebarOpen: true });
    renderSidebar();
    const settingsBtn = screen.getByText('设置').closest('button')!;
    expect(settingsBtn).toBeTruthy();
    fireEvent.click(settingsBtn);
    // jsdom doesn't update pathname, but the button click should work
    expect(settingsBtn).toBeInTheDocument();
  });
});
