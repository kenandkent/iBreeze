import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Sidebar } from './Sidebar';
import { useAppStore } from '../../stores/appStore';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const NAV_LABELS = [
  '公司管理',
  '员工管理',
  '任务看板',
  '知识库',
  '能力管理',
  '技能管理',
  'Prompt 资产',
  '员工模板',
  '设置',
] as const;

const NAV_KEYS = [
  'companies',
  'employees',
  'tasks',
  'knowledge',
  'capabilities',
  'skills',
  'prompts',
  'templates',
  'settings',
] as const;

describe('Sidebar', () => {
  it('renders all 9 nav items when open', () => {
    useAppStore.setState({ sidebarOpen: true, currentPage: 'companies' });
    render(<Sidebar />);
    for (const label of NAV_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('hides nav labels when collapsed', () => {
    useAppStore.setState({ sidebarOpen: false });
    render(<Sidebar />);
    for (const label of NAV_LABELS) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it('shows iBreeze title when open', () => {
    useAppStore.setState({ sidebarOpen: true });
    render(<Sidebar />);
    expect(screen.getByText('iBreeze')).toBeInTheDocument();
  });

  it('hides iBreeze title when collapsed', () => {
    useAppStore.setState({ sidebarOpen: false });
    render(<Sidebar />);
    expect(screen.queryByText('iBreeze')).not.toBeInTheDocument();
  });

  it('highlights current page with bg-blue-50', () => {
    useAppStore.setState({ sidebarOpen: true, currentPage: 'tasks' });
    render(<Sidebar />);
    const taskBtn = screen.getByText('任务看板').closest('button')!;
    expect(taskBtn.className).toContain('bg-blue-50');
    expect(taskBtn.className).toContain('text-blue-700');
  });

  it('non-current page does not have bg-blue-50', () => {
    useAppStore.setState({ sidebarOpen: true, currentPage: 'tasks' });
    render(<Sidebar />);
    const companiesBtn = screen.getByText('公司管理').closest('button')!;
    expect(companiesBtn.className).not.toContain('bg-blue-50');
  });

  it('toggles sidebar on button click', () => {
    useAppStore.setState({ sidebarOpen: true });
    render(<Sidebar />);
    const toggleBtn = document.querySelector('button.p-1')!;
    expect(toggleBtn).toBeTruthy();
    fireEvent.click(toggleBtn);
    expect(useAppStore.getState().sidebarOpen).toBe(false);
  });

  it('clicking nav item changes current page', () => {
    useAppStore.setState({ sidebarOpen: true, currentPage: 'companies' });
    render(<Sidebar />);
    fireEvent.click(screen.getByText('设置'));
    expect(useAppStore.getState().currentPage).toBe('settings');
  });

  it('clicking nav item updates store for every page', () => {
    useAppStore.setState({ sidebarOpen: true, currentPage: 'companies' });
    render(<Sidebar />);
    for (let i = 0; i < NAV_LABELS.length; i++) {
      fireEvent.click(screen.getByText(NAV_LABELS[i]));
      expect(useAppStore.getState().currentPage).toBe(NAV_KEYS[i]);
    }
  });
});
