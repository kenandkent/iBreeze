import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import DashboardPage from './pages/DashboardPage';
import CompanyPage from './pages/CompanyPage';
import ConversationPage from './pages/ConversationPage';
import KnowledgePage from './pages/KnowledgePage';
import WorkspacePage from './pages/WorkspacePage';
import OrchestrationPage from './pages/OrchestrationPage';
import AgentPage from './pages/AgentPage';
import AuditLogPage from './pages/AuditLogPage';
import LoginPage from './pages/LoginPage';

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
            <Route path="/login" element={<LoginPage />} />
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
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}

export default App;
