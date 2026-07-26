import type { RouteObject } from 'react-router-dom';
import { Navigate } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { Spin } from 'antd';
import { OriginGuard, AuthGuard } from './guards';

const Layout = lazy(() => import('../components/Layout'));
const ServerPage = lazy(() => import('../pages/ServerPage'));
const LoginPage = lazy(() => import('../pages/LoginPage'));
const RegisterPage = lazy(() => import('../pages/RegisterPage'));
const ChangePasswordPage = lazy(() => import('../pages/ChangePasswordPage'));
const OfflineUnlockPage = lazy(() => import('../pages/OfflineUnlockPage'));
const DashboardPage = lazy(() => import('../pages/DashboardPage'));
const CompanyPage = lazy(() => import('../pages/CompanyPage'));
const ConversationPage = lazy(() => import('../pages/ConversationPage'));
const KnowledgePage = lazy(() => import('../pages/KnowledgePage'));
const WorkspacePage = lazy(() => import('../pages/WorkspacePage'));
const OrchestrationPage = lazy(() => import('../pages/OrchestrationPage'));
const AgentPage = lazy(() => import('../pages/AgentPage'));
const AuditLogPage = lazy(() => import('../pages/AuditLogPage'));
const BackupPage = lazy(() => import('../pages/BackupPage'));
const ReviewPage = lazy(() => import('../pages/ReviewPage'));
const ApprovalListPage = lazy(() => import('../pages/ApprovalListPage'));
const SettingsPage = lazy(() => import('../pages/SettingsPage'));
const DiagnosticsPage = lazy(() => import('../pages/DiagnosticsPage'));
const DepartmentPage = lazy(() => import('../pages/DepartmentPage'));
const EmployeePage = lazy(() => import('../pages/EmployeePage'));
const TaskListPage = lazy(() => import('../pages/TaskListPage'));
const TaskDetailPage = lazy(() => import('../pages/TaskDetailPage'));
const SkillsPage = lazy(() => import('../pages/SkillsPage'));
const RecoveryPage = lazy(() => import('../pages/RecoveryPage'));

function Loading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Spin size="large" />
    </div>
  );
}

function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Loading />}>{children}</Suspense>;
}

export const routes: RouteObject[] = [
  {
    path: '/auth/server',
    element: <SuspenseWrapper><ServerPage /></SuspenseWrapper>,
  },
  {
    path: '/login',
    element: <SuspenseWrapper><LoginPage /></SuspenseWrapper>,
  },
  {
    path: '/register',
    element: <SuspenseWrapper><RegisterPage /></SuspenseWrapper>,
  },
  {
    path: '/auth/change-password',
    element: <SuspenseWrapper><ChangePasswordPage /></SuspenseWrapper>,
  },
  {
    path: '/offline-unlock',
    element: <SuspenseWrapper><OfflineUnlockPage /></SuspenseWrapper>,
  },
  {
    path: '/',
    element: (
      <OriginGuard>
        <AuthGuard>
          <SuspenseWrapper><Layout /></SuspenseWrapper>
        </AuthGuard>
      </OriginGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      {
        path: 'dashboard',
        element: <SuspenseWrapper><DashboardPage /></SuspenseWrapper>,
      },
      {
        path: 'companies',
        element: <SuspenseWrapper><CompanyPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/departments',
        element: <SuspenseWrapper><DepartmentPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/employees',
        element: <SuspenseWrapper><EmployeePage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/tasks',
        element: <SuspenseWrapper><TaskListPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/tasks/:taskId',
        element: <SuspenseWrapper><TaskDetailPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/conversations',
        element: <SuspenseWrapper><ConversationPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/knowledge',
        element: <SuspenseWrapper><KnowledgePage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/workspaces',
        element: <SuspenseWrapper><WorkspacePage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/orchestrations',
        element: <SuspenseWrapper><OrchestrationPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/agents',
        element: <SuspenseWrapper><AgentPage /></SuspenseWrapper>,
      },
      {
        path: 'companies/:companyId/reviews',
        element: <SuspenseWrapper><ReviewPage /></SuspenseWrapper>,
      },
      {
        path: 'conversations',
        element: <SuspenseWrapper><ConversationPage /></SuspenseWrapper>,
      },
      {
        path: 'knowledge',
        element: <SuspenseWrapper><KnowledgePage /></SuspenseWrapper>,
      },
      {
        path: 'workspaces',
        element: <SuspenseWrapper><WorkspacePage /></SuspenseWrapper>,
      },
      {
        path: 'orchestrations',
        element: <SuspenseWrapper><OrchestrationPage /></SuspenseWrapper>,
      },
      {
        path: 'agents',
        element: <SuspenseWrapper><AgentPage /></SuspenseWrapper>,
      },
      {
        path: 'audit-logs',
        element: <SuspenseWrapper><AuditLogPage /></SuspenseWrapper>,
      },
      {
        path: 'settings',
        element: <SuspenseWrapper><SettingsPage /></SuspenseWrapper>,
      },
      {
        path: 'diagnostics',
        element: <SuspenseWrapper><DiagnosticsPage /></SuspenseWrapper>,
      },
      {
        path: 'departments',
        element: <SuspenseWrapper><DepartmentPage /></SuspenseWrapper>,
      },
      {
        path: 'employees',
        element: <SuspenseWrapper><EmployeePage /></SuspenseWrapper>,
      },
      {
        path: 'tasks',
        element: <SuspenseWrapper><TaskListPage /></SuspenseWrapper>,
      },
      {
        path: 'tasks/:id',
        element: <SuspenseWrapper><TaskDetailPage /></SuspenseWrapper>,
      },
      {
        path: 'skills',
        element: <SuspenseWrapper><SkillsPage /></SuspenseWrapper>,
      },
      {
        path: 'backups',
        element: <SuspenseWrapper><BackupPage /></SuspenseWrapper>,
      },
      {
        path: 'reviews',
        element: <SuspenseWrapper><ReviewPage /></SuspenseWrapper>,
      },
      {
        path: 'approvals',
        element: <SuspenseWrapper><ApprovalListPage /></SuspenseWrapper>,
      },
    ],
  },
  {
    path: '/recovery',
    element: <SuspenseWrapper><RecoveryPage /></SuspenseWrapper>,
  },
];
