import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '../../stores/appStore';
import { ErrorBoundary } from '../common/ErrorBoundary';
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
import { GovernancePage } from '../governance/GovernancePage';
import { KnowledgeGovernancePage } from '../knowledge/KnowledgeGovernancePage';
import { PermissionPage } from '../permission/PermissionPage';
import { CapabilityEnginePage } from '../capability/CapabilityEnginePage';
import { TaskAdvancedPage } from '../task/TaskAdvancedPage';

const PAGE_LABELS: Record<string, string> = {
  companies: '公司管理',
  employees: '员工管理',
  tasks: '任务看板',
  knowledge: '知识库',
  capabilities: '能力管理',
  skills: '技能管理',
  prompts: 'Prompt 资产',
  templates: '员工模板',
  session: '会话',
  provider: 'Provider与Backend',
  grant: '授权',
  intervention: '人工干预',
  audit: '审计',
  dashboard: 'Dashboard',
  governance: '治理与审批',
  knowledgeGov: '知识治理',
  permission: '权限可视化',
  capengine: '能力引擎',
  taskAdvanced: '任务高级',
  settings: '设置',
};

function PageContent() {
  const { currentPage, currentCompanyId } = useAppStore();
  const label = PAGE_LABELS[currentPage] ?? currentPage;
  let content: React.ReactNode;

  switch (currentPage) {
    case 'companies':
      content = <CompanyList />; break;
    case 'employees':
      content = <EmployeeList />; break;
    case 'tasks':
      content = <TaskBoard />; break;
    case 'knowledge':
      content = <KnowledgeList />; break;
    case 'capabilities':
      content = <CapabilityList companyId={currentCompanyId} />; break;
    case 'skills':
      content = <SkillList companyId={currentCompanyId} />; break;
    case 'prompts':
      content = <PromptList companyId={currentCompanyId} />; break;
    case 'templates':
      content = <TemplateList companyId={currentCompanyId} />; break;
    case 'session':
      content = <SessionPage />; break;
    case 'provider':
      content = <ProviderBackendPage />; break;
    case 'grant':
      content = <GrantPage />; break;
    case 'intervention':
      content = <InterventionPage />; break;
    case 'audit':
      content = <AuditPage />; break;
    case 'governance':
      content = <GovernancePage />; break;
    case 'knowledgeGov':
      content = <KnowledgeGovernancePage />; break;
    case 'permission':
      content = <PermissionPage />; break;
    case 'capengine':
      content = <CapabilityEnginePage />; break;
    case 'taskAdvanced':
      content = <TaskAdvancedPage />; break;
    case 'dashboard':
      content = <DashboardPage />; break;
    case 'settings':
      content = <SettingsPage />; break;
    default:
      content = <CompanyList />; break;
  }

  return <ErrorBoundary fallbackLabel={label}>{content}</ErrorBoundary>;
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
