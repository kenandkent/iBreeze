import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from './appStore';

describe('appStore', () => {
  beforeEach(() => {
    useAppStore.setState({
      currentPage: 'companies',
      currentCompanyId: null,
      sidebarOpen: true,
    });
  });

  it('has initial state', () => {
    const state = useAppStore.getState();
    expect(state.currentPage).toBe('companies');
    expect(state.currentCompanyId).toBeNull();
    expect(state.sidebarOpen).toBe(true);
  });

  it('sets current page', () => {
    useAppStore.getState().setCurrentPage('employees');
    expect(useAppStore.getState().currentPage).toBe('employees');
  });

  it('sets current company', () => {
    useAppStore.getState().setCurrentCompany('comp-123');
    expect(useAppStore.getState().currentCompanyId).toBe('comp-123');
  });

  it('clears current company', () => {
    useAppStore.getState().setCurrentCompany('comp-123');
    useAppStore.getState().setCurrentCompany(null);
    expect(useAppStore.getState().currentCompanyId).toBeNull();
  });

  it('toggles sidebar', () => {
    expect(useAppStore.getState().sidebarOpen).toBe(true);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarOpen).toBe(false);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarOpen).toBe(true);
  });

  it('sets page to tasks', () => {
    useAppStore.getState().setCurrentPage('tasks');
    expect(useAppStore.getState().currentPage).toBe('tasks');
  });

  it('sets page to settings', () => {
    useAppStore.getState().setCurrentPage('settings');
    expect(useAppStore.getState().currentPage).toBe('settings');
  });
});
