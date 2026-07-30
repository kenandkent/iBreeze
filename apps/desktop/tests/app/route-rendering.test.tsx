import { vi } from 'vitest';
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
vi.mock('../../src/pages/DashboardPage', () => ({ default: mockComponent('DashboardPage') }));
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
vi.mock('../../src/components/Layout', () => ({ default: mockComponent('Layout') }));

vi.mock('antd', async () => {
  const React = await import('react');
  return {
    Spin: (props: Record<string, unknown>) =>
      React.createElement('div', { 'data-testid': 'Spin' }, props.children as React.ReactNode),
  };
});

import { describe, it, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRoutes } from 'react-router-dom';
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

describe('route rendering - auth routes', () => {
  beforeEach(() => {
    queryClient.clear();
  });

  const authPaths = [
    '/auth/server',
    '/login',
    '/register',
    '/auth/change-password',
    '/offline-unlock',
    '/recovery',
  ];

  for (const path of authPaths) {
    it(`renders ${path}`, async () => {
      const { unmount } = renderRoute(path);
      await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
      unmount();
    });
  }
});

describe('route rendering - guarded routes', () => {
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

  const guardedPaths = [
    '/dashboard',
    '/companies',
    '/settings',
    '/diagnostics',
    '/backups',
  ];

  for (const path of guardedPaths) {
    it(`renders ${path}`, async () => {
      const { unmount } = renderRoute(path);
      await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
      unmount();
    });
  }
});

describe('route rendering - company-scoped routes', () => {
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

  const companyPaths = [
    '/companies/c1/dashboard',
    '/companies/c1/departments',
    '/companies/c1/employees',
    '/companies/c1/tasks',
    '/companies/c1/conversations',
    '/companies/c1/knowledge',
    '/companies/c1/workspaces',
    '/companies/c1/orchestrations',
    '/companies/c1/agents',
    '/companies/c1/reviews',
    '/companies/c1/audit-logs',
    '/companies/c1/settings',
    '/companies/c1/diagnostics',
    '/companies/c1/skills',
    '/companies/c1/backups',
    '/companies/c1/approvals',
  ];

  for (const path of companyPaths) {
    it(`renders ${path}`, async () => {
      const { unmount } = renderRoute(path);
      await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
      unmount();
    });
  }
});
