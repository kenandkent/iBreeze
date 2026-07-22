import {
  Building2,
  Users,
  ClipboardList,
  Settings,
  PanelLeftClose,
  PanelLeft,
  MessageSquare,
  LayoutDashboard,
  GitBranch,
} from 'lucide-react';
import clsx from 'clsx';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppStore } from '../../stores/appStore';

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/companies', label: '公司管理', icon: <Building2 size={18} /> },
  { path: '/employees', label: '员工管理', icon: <Users size={18} /> },
  { path: '/session', label: '会话', icon: <MessageSquare size={18} /> },
  { path: '/tasks', label: '任务看板', icon: <ClipboardList size={18} /> },
  { path: '/tasks/advanced', label: '任务高级', icon: <GitBranch size={18} /> },
  { path: '/dashboard', label: '概览', icon: <LayoutDashboard size={18} /> },
  { path: '/settings', label: '设置', icon: <Settings size={18} /> },
];

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarOpen, toggleSidebar } = useAppStore();

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
        {NAV_ITEMS.map((item) => {
          const isActive = item.path === '/tasks/advanced'
            ? location.pathname === '/tasks/advanced'
            : item.path === '/tasks'
              ? location.pathname === '/tasks'
              : item.path === '/session'
                ? location.pathname === '/session' || location.pathname === '/'
                : location.pathname === item.path || location.pathname.startsWith(item.path + '/');
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={clsx(
                'flex items-center gap-2 w-full px-3 py-2 text-sm rounded-md transition-colors',
                isActive
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-50'
              )}
            >
              {item.icon}
              {sidebarOpen && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
