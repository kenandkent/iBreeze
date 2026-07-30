import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '../../src/stores/appStore';

describe('useAppStore', () => {
  beforeEach(() => {
    useAppStore.setState({
      sidebarCollapsed: false,
      theme: 'light',
      notifications: [],
      selectedCompanyId: null,
    });
  });

  it('has correct initial state', () => {
    const state = useAppStore.getState();
    expect(state.sidebarCollapsed).toBe(false);
    expect(state.theme).toBe('light');
    expect(state.notifications).toEqual([]);
    expect(state.selectedCompanyId).toBeNull();
  });

  it('toggleSidebar toggles sidebarCollapsed', () => {
    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
  });

  it('setTheme updates theme', () => {
    useAppStore.getState().setTheme('dark');
    expect(useAppStore.getState().theme).toBe('dark');
    useAppStore.getState().setTheme('light');
    expect(useAppStore.getState().theme).toBe('light');
  });

  it('addNotification adds a notification', () => {
    useAppStore.getState().addNotification('info', 'Test message');
    const notifications = useAppStore.getState().notifications;
    expect(notifications).toHaveLength(1);
    expect(notifications[0].type).toBe('info');
    expect(notifications[0].message).toBe('Test message');
    expect(notifications[0].id).toBeDefined();
    expect(notifications[0].timestamp).toBeGreaterThan(0);
  });

  it('addNotification generates unique ids', () => {
    useAppStore.getState().addNotification('info', 'First');
    useAppStore.getState().addNotification('info', 'Second');
    const notifications = useAppStore.getState().notifications;
    expect(notifications).toHaveLength(2);
    expect(notifications[0].id).not.toBe(notifications[1].id);
  });

  it('removeNotification removes by id', () => {
    useAppStore.getState().addNotification('info', 'Test');
    const id = useAppStore.getState().notifications[0].id;
    useAppStore.getState().removeNotification(id);
    expect(useAppStore.getState().notifications).toHaveLength(0);
  });

  it('removeNotification does nothing for unknown id', () => {
    useAppStore.getState().addNotification('info', 'Test');
    useAppStore.getState().removeNotification('unknown-id');
    expect(useAppStore.getState().notifications).toHaveLength(1);
  });

  it('setSelectedCompany updates selectedCompanyId', () => {
    useAppStore.getState().setSelectedCompany('company-1');
    expect(useAppStore.getState().selectedCompanyId).toBe('company-1');
  });

  it('setSelectedCompany can set null', () => {
    useAppStore.getState().setSelectedCompany('company-1');
    useAppStore.getState().setSelectedCompany(null);
    expect(useAppStore.getState().selectedCompanyId).toBeNull();
  });
});
