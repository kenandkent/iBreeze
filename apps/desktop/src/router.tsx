import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { SidecarGuard } from './components/common/SidecarGuard';
import { CompanyList } from './components/company/CompanyList';
import { CompanyDetail } from './components/company/CompanyDetail';
import { EmployeeList } from './components/employee/EmployeeList';
import { EmployeeDetail } from './components/employee/EmployeeDetail';
import { SessionPage } from './components/session/SessionPage';
import { TaskBoard } from './components/task/TaskBoard';
import { TaskAdvancedPage } from './components/task/TaskAdvancedPage';
import { DashboardPage } from './components/dashboard/DashboardPage';
import { SettingsPage } from './components/settings/SettingsPage';
import { LoadingSpinner } from './components/common/LoadingSpinner';
import { rpcCall } from './services/rpcClient';
import type { Company, Employee } from './types';

function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const { data: company, isLoading } = useQuery<Company>({
    queryKey: ['company', companyId],
    queryFn: () => rpcCall<Company>('org.company.get', { company_id: companyId }),
    enabled: !!companyId,
  });

  if (isLoading) return <LoadingSpinner />;
  if (!company) return <div className="p-6 text-sm text-gray-500">公司不存在</div>;
  return <CompanyDetail company={company} />;
}

function EmployeeDetailPage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const { data: employee, isLoading } = useQuery<Employee>({
    queryKey: ['employee', employeeId],
    queryFn: () => rpcCall<Employee>('org.employee.get', { employee_id: employeeId }),
    enabled: !!employeeId,
  });

  if (isLoading) return <LoadingSpinner />;
  if (!employee) return <div className="p-6 text-sm text-gray-500">员工不存在</div>;
  return <EmployeeDetail employee={employee} />;
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <SidecarGuard><Layout /></SidecarGuard>,
    children: [
      { index: true, element: <SessionPage /> },
      { path: 'companies', element: <CompanyList /> },
      { path: 'companies/:companyId', element: <CompanyDetailPage /> },
      { path: 'employees', element: <EmployeeList /> },
      { path: 'employees/:employeeId', element: <EmployeeDetailPage /> },
      { path: 'session', element: <SessionPage /> },
      { path: 'tasks', element: <TaskBoard /> },
      { path: 'tasks/advanced', element: <TaskAdvancedPage /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
