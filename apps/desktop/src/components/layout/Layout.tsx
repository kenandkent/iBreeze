import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '../../stores/appStore';
import { CompanyList } from '../company/CompanyList';
import { EmployeeList } from '../employee/EmployeeList';
import { TaskBoard } from '../task/TaskBoard';
import { KnowledgeList } from '../knowledge/KnowledgeList';
import { CapabilityList } from '../capability/CapabilityList';
import { SkillList } from '../capability/SkillList';
import { PromptList } from '../capability/PromptList';
import { TemplateList } from '../capability/TemplateList';
import { SettingsPage } from '../settings/SettingsPage';
import { SessionPage } from '../session/SessionPage';
import { ProviderBackendPage } from '../provider/ProviderBackendPage';
import { GrantPage } from '../grant/GrantPage';
import { InterventionPage } from '../intervention/InterventionPage';
import { AuditPage } from '../audit/AuditPage';
import { DashboardPage } from '../dashboard/DashboardPage';

function PageContent() {
  const { currentPage, currentCompanyId } = useAppStore();
  switch (currentPage) {
    case 'companies':
      return <CompanyList />;
    case 'employees':
      return <EmployeeList />;
    case 'tasks':
      return <TaskBoard />;
    case 'knowledge':
      return <KnowledgeList />;
    case 'capabilities':
      return <CapabilityList companyId={currentCompanyId} />;
    case 'skills':
      return <SkillList companyId={currentCompanyId} />;
    case 'prompts':
      return <PromptList companyId={currentCompanyId} />;
    case 'templates':
      return <TemplateList companyId={currentCompanyId} />;
    case 'session':
      return <SessionPage />;
    case 'provider':
      return <ProviderBackendPage />;
    case 'grant':
      return <GrantPage />;
    case 'intervention':
      return <InterventionPage />;
    case 'audit':
      return <AuditPage />;
    case 'dashboard':
      return <DashboardPage />;
    case 'settings':
      return <SettingsPage />;
    default:
      return <CompanyList />;
  }
}

export function Layout() {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-auto">
          <PageContent />
        </main>
      </div>
    </div>
  );
}
