import { RefreshCw } from 'lucide-react';
import { useAppStore } from '../../stores/appStore';

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
  const { currentPage } = useAppStore();

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
      <h1 className="text-lg font-semibold text-gray-800">
        {PAGE_TITLES[currentPage] ?? 'iBreeze'}
      </h1>
      {onRefresh && (
        <button
          onClick={onRefresh}
          className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 rounded-md hover:bg-gray-100 transition-colors"
        >
          <RefreshCw size={14} />
          刷新
        </button>
      )}
    </header>
  );
}
