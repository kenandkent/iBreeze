import { useQuery } from '@tanstack/react-query';
import { RefreshCw, Building2 } from 'lucide-react';
import { useAppStore } from '../../stores/appStore';
import { rpcCall } from '../../services/rpcClient';
import type { Company } from '../../types';

const PAGE_TITLES: Record<string, string> = {
  companies: '公司管理',
  employees: '员工管理',
  tasks: '任务看板',
  knowledge: '知识库',
  capabilities: '能力管理',
  skills: '技能管理',
  prompts: 'Prompt 资产',
  templates: '员工模板',
  settings: '设置',
};

export function Header({ onRefresh }: { onRefresh?: () => void }) {
  const { currentPage, currentCompanyId, setCurrentCompany } = useAppStore();

  const { data: companies } = useQuery<Company[]>({
    queryKey: ['companies'],
    queryFn: () => rpcCall<Company[]>('org.company.list'),
    retry: 2,
    retryDelay: 1000,
  });

  const activeCompanies = companies?.filter((c) => c.status === 'active') ?? [];

  if (activeCompanies.length > 0 && !currentCompanyId) {
    setCurrentCompany(activeCompanies[0].company_id);
  }

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
      <h1 className="text-lg font-semibold text-gray-800">
        {PAGE_TITLES[currentPage] ?? 'iBreeze'}
      </h1>
      <div className="flex items-center gap-3">
        {activeCompanies.length > 0 && (
          <div className="flex items-center gap-2">
            <Building2 size={14} className="text-gray-400" />
            <select
              value={currentCompanyId ?? ''}
              onChange={(e) => setCurrentCompany(e.target.value || null)}
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
