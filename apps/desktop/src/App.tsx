import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import DashboardPage from "./pages/DashboardPage";
import CompanyPage from "./pages/CompanyPage";
import ConversationPage from "./pages/ConversationPage";
import KnowledgePage from "./pages/KnowledgePage";
import WorkspacePage from "./pages/WorkspacePage";
import OrchestrationPage from "./pages/OrchestrationPage";
import AgentPage from "./pages/AgentPage";
import AuditLogPage from "./pages/AuditLogPage";
import BackupPage from "./pages/BackupPage";
import ReviewPage from "./pages/ReviewPage";
import ApprovalListPage from "./pages/ApprovalListPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ServerPage from "./pages/ServerPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import OfflineUnlockPage from "./pages/OfflineUnlockPage";
import SettingsPage from "./pages/SettingsPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import DepartmentPage from "./pages/DepartmentPage";
import EmployeePage from "./pages/EmployeePage";
import TaskListPage from "./pages/TaskListPage";
import TaskDetailPage from "./pages/TaskDetailPage";
import SkillsPage from "./pages/SkillsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <Routes>
            <Route path="/auth/server" element={<ServerPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/auth/change-password" element={<ChangePasswordPage />} />
            <Route path="/offline-unlock" element={<OfflineUnlockPage />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="companies" element={<CompanyPage />} />
              <Route path="conversations" element={<ConversationPage />} />
              <Route path="knowledge" element={<KnowledgePage />} />
              <Route path="workspaces" element={<WorkspacePage />} />
              <Route path="orchestrations" element={<OrchestrationPage />} />
              <Route path="agents" element={<AgentPage />} />
              <Route path="audit-logs" element={<AuditLogPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="diagnostics" element={<DiagnosticsPage />} />
              <Route path="departments" element={<DepartmentPage />} />
              <Route path="employees" element={<EmployeePage />} />
              <Route path="tasks" element={<TaskListPage />} />
              <Route path="tasks/:id" element={<TaskDetailPage />} />
              <Route path="skills" element={<SkillsPage />} />
              <Route path="backups" element={<BackupPage />} />
              <Route path="reviews" element={<ReviewPage />} />
              <Route path="approvals" element={<ApprovalListPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}

export default App;
