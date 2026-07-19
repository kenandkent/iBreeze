import type { Company } from '../../types';
import { StatusBadge } from '../common/StatusBadge';

export function CompanyDetail({ company }: { company: Company }) {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-gray-800">{company.name}</h2>
        <StatusBadge status={company.status} />
      </div>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-500">ID</span>
          <p className="font-mono text-gray-700 mt-0.5">{company.company_id}</p>
        </div>
        <div>
          <span className="text-gray-500">创建时间</span>
          <p className="text-gray-700 mt-0.5">{company.created_at}</p>
        </div>
      </div>
    </div>
  );
}
