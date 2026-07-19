import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatNumber } from '../../utils/format';
import type { Backend, Provider, ProviderModel } from '../../types';
import { Server } from 'lucide-react';

export function ProviderBackendPage() {
  const { currentCompanyId } = useAppStore();
  const [activeProviderId, setActiveProviderId] = useState<string | null>(null);

  const { data: backends, isLoading, error, refetch } = useQuery<Backend[]>({
    queryKey: ['backend', currentCompanyId],
    queryFn: () => rpcCall<Backend[]>('backend.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: providers } = useQuery<Provider[]>({
    queryKey: ['provider', currentCompanyId],
    queryFn: () => rpcCall<Provider[]>('provider.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: models } = useQuery<ProviderModel[]>({
    queryKey: ['providerModels', activeProviderId],
    queryFn: () =>
      rpcCall<ProviderModel[]>('provider.model.list', {
        company_id: currentCompanyId,
        provider_id: activeProviderId,
      }),
    enabled: !!activeProviderId && !!currentCompanyId,
  });

  if (!currentCompanyId) {
    return (
      <div className="p-6 text-sm text-amber-600">请先在上方选择公司后再查看 Provider 与 Backend。</div>
    );
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    console.error('[iBreeze] ProviderBackendPage: load failed', error);
    return (
      <div className="p-6">
        <div className="text-red-500 text-sm mb-4">加载失败: {error.message}</div>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          重试
        </button>
      </div>
    );
  }

  const onOp = (method: string, params: Record<string, unknown>) => {
    rpcCall(method, params).then(() => refetch());
  };

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-base font-medium text-gray-700">Provider 与 Backend</h2>

      <section>
        <h3 className="text-sm font-medium text-gray-600 mb-2">Backend</h3>
        {!backends || backends.length === 0 ? (
          <div className="text-center py-8 text-gray-400">
            <Server className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-sm">暂无 Backend</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">名称</th>
                  <th className="px-4 py-2 font-medium">类型</th>
                  <th className="px-4 py-2 font-medium">状态</th>
                  <th className="px-4 py-2 font-medium">健康</th>
                  <th className="px-4 py-2 font-medium">容量</th>
                  <th className="px-4 py-2 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {backends.map((b) => (
                  <tr key={b.backend_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-medium text-gray-800">{b.name}</td>
                    <td className="px-4 py-2.5 text-gray-600">{b.type}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={b.status} /></td>
                    <td className="px-4 py-2.5"><StatusBadge status={b.health} /></td>
                    <td className="px-4 py-2.5 text-gray-600">{formatNumber(b.capacity)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => onOp('backend.probe', { backend_id: b.backend_id })} className="text-xs text-gray-500 hover:text-blue-500 px-1.5 py-1 rounded hover:bg-gray-100">探测</button>
                        <button onClick={() => onOp('backend.enable', { backend_id: b.backend_id })} className="text-xs text-gray-500 hover:text-green-500 px-1.5 py-1 rounded hover:bg-gray-100">启用</button>
                        <button onClick={() => onOp('backend.drain', { backend_id: b.backend_id })} className="text-xs text-gray-500 hover:text-amber-500 px-1.5 py-1 rounded hover:bg-gray-100">排空</button>
                        <button onClick={() => onOp('backend.archive', { backend_id: b.backend_id })} className="text-xs text-gray-500 hover:text-red-500 px-1.5 py-1 rounded hover:bg-gray-100">归档</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h3 className="text-sm font-medium text-gray-600 mb-2">Provider</h3>
        {!providers || providers.length === 0 ? (
          <p className="text-sm text-gray-400">暂无 Provider</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <tbody className="divide-y divide-gray-100">
                  {providers.map((p) => (
                    <tr
                      key={p.provider_id}
                      onClick={() => setActiveProviderId(p.provider_id)}
                      className={`cursor-pointer hover:bg-gray-50 ${activeProviderId === p.provider_id ? 'bg-blue-50' : ''}`}
                    >
                      <td className="px-4 py-2.5 font-medium text-gray-800">{p.name}</td>
                      <td className="px-4 py-2.5 text-gray-600">{p.type}</td>
                      <td className="px-4 py-2.5"><StatusBadge status={p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 p-4">
              {!activeProviderId ? (
                <p className="text-sm text-gray-400">请选择 Provider 查看模型</p>
              ) : !models || models.length === 0 ? (
                <p className="text-sm text-gray-400">该 Provider 暂无模型</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {models.map((m) => (
                    <li key={m.model_id} className="text-gray-700">
                      {m.name}
                      <button
                        onClick={() => rpcCall('provider.pricingPolicy.update', { provider_id: m.provider_id, company_id: currentCompanyId, policy: {} })}
                        className="ml-2 text-xs text-blue-500 hover:underline"
                      >
                        更新定价策略
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
