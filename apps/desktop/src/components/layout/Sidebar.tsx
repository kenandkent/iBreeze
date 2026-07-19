import {
  Building2,
  Users,
  ClipboardList,
  BookOpen,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Cpu,
  FileText,
  Puzzle,
  LayoutTemplate,
  MessageSquare,
  Server,
  KeyRound,
  AlertTriangle,
  ScrollText,
  LayoutDashboard,
} from 'lucide-react';
import clsx from 'clsx';
import { useAppStore } from '../../stores/appStore';
import type { PageKey } from '../../types';

interface NavItem {
  key: PageKey;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { key: 'companies', label: '公司管理', icon: <Building2 size={18} /> },
  { key: 'employees', label: '员工管理', icon: <Users size={18} /> },
  { key: 'tasks', label: '任务看板', icon: <ClipboardList size={18} /> },
  { key: 'knowledge', label: '知识库', icon: <BookOpen size={18} /> },
  { key: 'capabilities', label: '能力管理', icon: <Cpu size={18} /> },
  { key: 'skills', label: '技能管理', icon: <Puzzle size={18} /> },
  { key: 'prompts', label: 'Prompt 资产', icon: <FileText size={18} /> },
  { key: 'templates', label: '员工模板', icon: <LayoutTemplate size={18} /> },
  { key: 'session', label: '会话', icon: <MessageSquare size={18} /> },
  { key: 'provider', label: 'Provider与Backend', icon: <Server size={18} /> },
  { key: 'grant', label: '授权', icon: <KeyRound size={18} /> },
  { key: 'intervention', label: '人工干预', icon: <AlertTriangle size={18} /> },
  { key: 'audit', label: '审计', icon: <ScrollText size={18} /> },
  { key: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
  { key: 'settings', label: '设置', icon: <Settings size={18} /> },
];

export function Sidebar() {
  const { currentPage, setCurrentPage, sidebarOpen, toggleSidebar } = useAppStore();

  return (
    <aside
      className={clsx(
        'flex flex-col h-full bg-white border-r border-gray-200 transition-all duration-200',
        sidebarOpen ? 'w-52' : 'w-14'
      )}
    >
      <div className="flex items-center justify-between px-3 py-3 border-b border-gray-100">
        {sidebarOpen && (
          <span className="text-sm font-semibold text-gray-800 truncate">iBreeze</span>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1 rounded hover:bg-gray-100 text-gray-500"
        >
          {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeft size={16} />}
        </button>
      </div>
      <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            onClick={() => setCurrentPage(item.key)}
            className={clsx(
              'flex items-center gap-2 w-full px-3 py-2 text-sm rounded-md transition-colors',
              currentPage === item.key
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-gray-600 hover:bg-gray-50'
            )}
          >
            {item.icon}
            {sidebarOpen && <span className="truncate">{item.label}</span>}
          </button>
        ))}
      </nav>
    </aside>
  );
}
