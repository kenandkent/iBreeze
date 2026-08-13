import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';

const mockComponent = (name: string) => {
  const C = (props: Record<string, unknown>) =>
    React.createElement('div', { 'data-testid': name }, props.children as React.ReactNode);
  C.displayName = name;
  return C;
};

vi.mock('../../src/pages/ServerPage', () => ({ default: mockComponent('ServerPage') }));
vi.mock('../../src/pages/LoginPage', () => ({ default: mockComponent('LoginPage') }));
vi.mock('../../src/pages/RegisterPage', () => ({ default: mockComponent('RegisterPage') }));
vi.mock('../../src/pages/ChangePasswordPage', () => ({ default: mockComponent('ChangePasswordPage') }));
vi.mock('../../src/pages/OfflineUnlockPage', () => ({ default: mockComponent('OfflineUnlockPage') }));
// DashboardPage throws a pending promise while rendering, so Suspense shows
// the Loading fallback (and the unmocked Loading/Spin paths get covered).
const { suspenseThrower } = vi.hoisted(() => {
  const SuspenseTrigger = () => {
    throw new Promise(() => {});
  };
  return { suspenseThrower: SuspenseTrigger };
});
vi.mock('../../src/pages/DashboardPage', () => ({ default: suspenseThrower }));
vi.mock('../../src/pages/CompanyPage', () => ({ default: mockComponent('CompanyPage') }));
vi.mock('../../src/pages/ConversationPage', () => ({ default: mockComponent('ConversationPage') }));
vi.mock('../../src/pages/KnowledgePage', () => ({ default: mockComponent('KnowledgePage') }));
vi.mock('../../src/pages/WorkspacePage', () => ({ default: mockComponent('WorkspacePage') }));
vi.mock('../../src/pages/OrchestrationPage', () => ({ default: mockComponent('OrchestrationPage') }));
vi.mock('../../src/pages/AgentPage', () => ({ default: mockComponent('AgentPage') }));
vi.mock('../../src/pages/AuditLogPage', () => ({ default: mockComponent('AuditLogPage') }));
vi.mock('../../src/pages/BackupPage', () => ({ default: mockComponent('BackupPage') }));
vi.mock('../../src/pages/ReviewPage', () => ({ default: mockComponent('ReviewPage') }));
vi.mock('../../src/pages/ApprovalListPage', () => ({ default: mockComponent('ApprovalListPage') }));
vi.mock('../../src/pages/SettingsPage', () => ({ default: mockComponent('SettingsPage') }));
vi.mock('../../src/pages/DiagnosticsPage', () => ({ default: mockComponent('DiagnosticsPage') }));
vi.mock('../../src/pages/DepartmentPage', () => ({ default: mockComponent('DepartmentPage') }));
vi.mock('../../src/pages/EmployeePage', () => ({ default: mockComponent('EmployeePage') }));
vi.mock('../../src/pages/TaskListPage', () => ({ default: mockComponent('TaskListPage') }));
vi.mock('../../src/pages/TaskDetailPage', () => ({ default: mockComponent('TaskDetailPage') }));
vi.mock('../../src/pages/SkillsPage', () => ({ default: mockComponent('SkillsPage') }));
vi.mock('../../src/pages/RecoveryPage', () => ({ default: mockComponent('RecoveryPage') }));
vi.mock('../../src/pages/ProfileRoutingPage', () => ({ default: mockComponent('ProfileRoutingPage') }));
vi.mock('../../src/pages/RunRoutingPage', () => ({ default: mockComponent('RunRoutingPage') }));
// Layout must render an <Outlet/> so child routes are actually mounted.
vi.mock('../../src/components/Layout', async () => {
  const React = await import('react');
  const { Outlet } = await import('react-router-dom');
  const C = () => React.createElement('div', { 'data-testid': 'Layout' }, React.createElement(Outlet));
  C.displayName = 'Layout';
  return { default: C };
});

vi.mock('antd', async () => {
  const React = await import('react');
  return {
    Spin: (props: Record<string, unknown>) =>
      React.createElement('div', { 'data-testid': 'Spin' }, props.children as React.ReactNode),
  };
});

import { render, act, screen } from '@testing-library/react';
import { MemoryRouter, useRoutes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from '../../src/stores/authStore';
import { useAppStore } from '../../src/stores/appStore';
import { routes } from '../../src/app/routes';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});

function AppRoutes() {
  return useRoutes(routes);
}

function renderRoute(path: string) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('route rendering - additional company-scoped paths', () => {
  beforeEach(() => {
    queryClient.clear();
    useAuthStore.setState({
      backendOrigin: 'https://test.com',
      profileOpened: true,
      profileDirectoryId: 'pd1',
      appUserId: 'u1',
      maskedIdentifier: 'u***@test.com',
      mode: 'online',
      catalogReleaseSequence: 1,
    });
    useAppStore.setState({ selectedCompanyId: 'c1' });
  });

  const extraPaths = [
    '/companies/c1/tasks/t1',
    '/companies/c1/profiles/p1/routing',
    '/companies/c1/runs/r1/routing',
  ];

  for (const path of extraPaths) {
    it(`renders ${path}`, async () => {
      const { unmount } = renderRoute(path);
      await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
      unmount();
    });
  }

  it('renders Suspense fallback (Loading) while a lazy page is pending', async () => {
    const { unmount } = renderRoute('/companies/c1/dashboard');
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(screen.getByTestId('Spin')).toBeDefined();
    unmount();
  });
});
