import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw, Building2 } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useAppStore } from '../../stores/appStore';
import { rpcCall } from '../../services/rpcClient';
import type { Company } from '../../types';

const PATH_TITLES: Record<string, string> = {
  '/dashboard': '概览',
  '/companies': '公司管理',
  '/employees': '员工管理',
  '/tasks': '任务看板',
  '/tasks/advanced': '任务高级',
  '/session': '会话',
  '/settings': '设置',
};

export function Header({ onRefresh }: { onRefresh?: () => void }) {
  const location = useLocation();
  const { currentCompanyId, setCurrentCompany } = useAppStore();

  const { data: companies } = useQuery<Company[]>({
    queryKey: ['companies'],
    queryFn: () => rpcCall<Company[]>('org.company.list'),
    retry: 2,
    retryDelay: 1000,
  });

  const activeCompanies = companies?.filter((c) => c.status === 'active') ?? [];

  useEffect(() => {
    if (activeCompanies.length > 0 && !currentCompanyId) {
      console.log('[iBreeze] Header: auto-selecting first company', activeCompanies[0].company_id);
      setCurrentCompany(activeCompanies[0].company_id);
    }
  }, [activeCompanies, currentCompanyId, setCurrentCompany]);

  const title = PATH_TITLES[location.pathname] ?? 'iBreeze';

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
      <h1 className="text-lg font-semibold text-gray-800">
        {title}
      </h1>
      <div className="flex items-center gap-3">
        {activeCompanies.length > 0 && (
          <div className="flex items-center gap-2">
            <Building2 size={14} className="text-gray-400" />
            <select
              value={currentCompanyId ?? ''}
              onChange={(e) => {
                const val = e.target.value || null;
                console.log('[iBreeze] Header: switching company to', val);
                setCurrentCompany(val);
              }}
              className="text-sm border border-gray-200 rounded-md px-2 py-1.5 focus:outline-none focus:border-blue-400 bg-white"
            >
              {activeCompanies.map((c) => (
                <option key={c.company_id} value={c.company_id}>{c.name}</option>
              ))}
            </select>
          </div>
        )}
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 rounded-md hover:bg-gray-100 transition-colors"
          >
            <RefreshCw size={14} />
            刷新
          </button>
        )}
      </div>
    </header>
  );
}
