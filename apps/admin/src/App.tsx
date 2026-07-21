import { Routes, Route, Navigate } from 'react-router-dom';
import BasicLayout from './layouts/BasicLayout';
import Login from './pages/login';
import CapabilityList from './pages/capabilities';
import SkillList from './pages/skills';
import PromptList from './pages/prompts';
import TemplateList from './pages/templates';
import CapabilityEngine from './pages/capability-engine';
import KnowledgeList from './pages/knowledge';
import KnowledgeGovernance from './pages/knowledge/governance';
import ProviderBackend from './pages/providers';
import Governance from './pages/governance';
import AuditLog from './pages/audit';
import Intervention from './pages/audit/interventions';

function Private({ children }: { children: React.ReactNode }) {
  if (!localStorage.getItem('access_token')) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Private><BasicLayout /></Private>}>
        <Route index element={<Navigate to="/capabilities" replace />} />
        <Route path="capabilities" element={<CapabilityList />} />
        <Route path="skills" element={<SkillList />} />
        <Route path="prompts" element={<PromptList />} />
        <Route path="templates" element={<TemplateList />} />
        <Route path="capability-engine" element={<CapabilityEngine />} />
        <Route path="knowledge" element={<KnowledgeList />} />
        <Route path="knowledge/governance" element={<KnowledgeGovernance />} />
        <Route path="providers" element={<ProviderBackend />} />
        <Route path="governance" element={<Governance />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="audit/interventions" element={<Intervention />} />
      </Route>
    </Routes>
  );
}
