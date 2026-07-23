import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import AgentCatalogPage from './pages/AgentCatalogPage';
import ModelCatalogPage from './pages/ModelCatalogPage';
import ProviderCatalogPage from './pages/ProviderCatalogPage';
import AdminUserPage from './pages/AdminUserPage';
import ReleasePage from './pages/ReleasePage';
import SkillPage from './pages/SkillPage';
import CompatibilityPage from './pages/CompatibilityPage';
import SettingsPage from './pages/SettingsPage';
import AdminAuditLogPage from './pages/AdminAuditLogPage';
import LoginPage from './pages/LoginPage';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route index element={<Navigate to="/agents" replace />} />
              <Route path="agents" element={<AgentCatalogPage />} />
              <Route path="models" element={<ModelCatalogPage />} />
              <Route path="providers" element={<ProviderCatalogPage />} />
              <Route path="users" element={<AdminUserPage />} />
              <Route path="releases" element={<ReleasePage />} />
              <Route path="skills" element={<SkillPage />} />
              <Route path="compatibility" element={<CompatibilityPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="audit-logs" element={<AdminAuditLogPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}

export default App;
