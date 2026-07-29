import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';

const AgentCatalogPage = lazy(() => import('./pages/AgentCatalogPage'));
const ModelCatalogPage = lazy(() => import('./pages/ModelCatalogPage'));
const ProviderCatalogPage = lazy(() => import('./pages/ProviderCatalogPage'));
const AdminUserPage = lazy(() => import('./pages/AdminUserPage'));
const ReleasePage = lazy(() => import('./pages/ReleasePage'));
const SkillPage = lazy(() => import('./pages/SkillPage'));
const EmergencyPage = lazy(() => import('./pages/EmergencyPage'));
const CompatibilityPage = lazy(() => import('./pages/CompatibilityPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const AdminAuditLogPage = lazy(() => import('./pages/AdminAuditLogPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));

const queryClient = new QueryClient();

function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Spin style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }} />}>{children}</Suspense>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<SuspenseWrapper><LoginPage /></SuspenseWrapper>} />
            <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route index element={<Navigate to="/agents" replace />} />
              <Route path="agents" element={<SuspenseWrapper><AgentCatalogPage /></SuspenseWrapper>} />
              <Route path="models" element={<SuspenseWrapper><ModelCatalogPage /></SuspenseWrapper>} />
              <Route path="providers" element={<SuspenseWrapper><ProviderCatalogPage /></SuspenseWrapper>} />
              <Route path="users" element={<SuspenseWrapper><AdminUserPage /></SuspenseWrapper>} />
              <Route path="releases" element={<SuspenseWrapper><ReleasePage /></SuspenseWrapper>} />
              <Route path="emergency" element={<SuspenseWrapper><EmergencyPage /></SuspenseWrapper>} />
              <Route path="skills" element={<SuspenseWrapper><SkillPage /></SuspenseWrapper>} />
              <Route path="compatibility" element={<SuspenseWrapper><CompatibilityPage /></SuspenseWrapper>} />
              <Route path="settings" element={<SuspenseWrapper><SettingsPage /></SuspenseWrapper>} />
              <Route path="audit-logs" element={<SuspenseWrapper><AdminAuditLogPage /></SuspenseWrapper>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}

export default App;
