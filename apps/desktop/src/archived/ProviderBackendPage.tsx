import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { useAppStore } from '../../stores/appStore';
import { formatNumber } from '../../utils/format';
import type { Backend, Provider, ProviderModel, CliAgentOption } from '../../types';
import { Server, Plus, X } from 'lucide-react';

export function ProviderBackendPage() {
  const { currentCompanyId } = useAppStore();
  const queryClient = useQueryClient();
  const [activeProviderId, setActiveProviderId] = useState<string | null>(null);
  const [showProviderModal, setShowProviderModal] = useState(false);
  const [showBackendModal, setShowBackendModal] = useState(false);
  const [providerForm, setProviderForm] = useState({
    name: '',
    provider_type: 'api' as 'api' | 'cli',
    api_vendor: 'openai' as 'openai' | 'deepseek' | 'anthropic' | 'third_party',
    api_key: '',
    base_url: '',
    agent: '',
    model: '',
    custom_model: '',
  });
  const [fetchedModels, setFetchedModels] = useState<{ model: string; display_name: string }[]>([]);
  const [fetchModelsError, setFetchModelsError] = useState<string | null>(null);
  const [isFetchingModels, setIsFetchingModels] = useState(false);
  const [backendForm, setBackendForm] = useState({ name: '', backend_type: 'local_process', workspace_root: '' });

  const { data: agents } = useQuery<CliAgentOption[]>({
    queryKey: ['cliAgents'],
    queryFn: async () => {
      const res = await rpcCall<{ agents: CliAgentOption[] }>('provider.agent.list', {});
      return res.agents ?? [];
    },
    enabled: showProviderModal,
  });

  const selectedAgent = agents?.find((a) => a.agent_id === providerForm.agent);
  const modelValue = providerForm.model === '__custom__' ? providerForm.custom_model : providerForm.model;

  useEffect(() => {
    if (providerForm.provider_type === 'cli' && selectedAgent && providerForm.model && providerForm.model !== '__custom__') {
      const valid = selectedAgent.models.some((m) => m.model === providerForm.model);
      if (!valid) setProviderForm((f) => ({ ...f, model: '' }));
    }
  }, [providerForm.provider_type, selectedAgent, providerForm.model]);

  const { data: backends, isLoading, error, refetch } = useQuery<Backend[]>({
    queryKey: ['backend', currentCompanyId],
    queryFn: () => rpcCall<Backend[]>('backend.list', { company_id: currentCompanyId }),
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: providers } = useQuery<Provider[]>({
    queryKey: ['provider', currentCompanyId],
    queryFn: async () => {
      const res = await rpcCall<{ items: Provider[]; tier_mapping: Record<string, string> }>('provider.list', { company_id: currentCompanyId });
      return res.items ?? [];
    },
    enabled: !!currentCompanyId,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: models } = useQuery<ProviderModel[]>({
    queryKey: ['providerModels', activeProviderId],
    queryFn: async () => {
      const res = await rpcCall<{ items: ProviderModel[] }>('provider.model.list', {
        company_id: currentCompanyId,
        provider_id: activeProviderId,
      });
      return res.items ?? [];
    },
    enabled: !!activeProviderId && !!currentCompanyId,
  });

  const createProviderMutation = useMutation({
    mutationFn: async () => {
      const name = providerForm.name.trim();
      if (providerForm.provider_type === 'cli') {
        return rpcCall('provider.create', {
          name,
          provider_type: 'cli',
          config: { agent: providerForm.agent, model: modelValue },
        });
      }
      const res = await rpcCall<{ provider_id: string }>('provider.create', {
        name,
        provider_type: 'api',
        model: modelValue,
        config: {
          ...(providerForm.base_url.trim() ? { base_url: providerForm.base_url.trim() } : {}),
          api_vendor: providerForm.api_vendor,
        },
      });
      if (providerForm.api_key.trim()) {
        await rpcCall('provider.credential.set', {
          company_id: currentCompanyId,
          provider_id: res.provider_id,
          credential: { api_key: providerForm.api_key.trim() },
        });
      }
      return res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['provider', currentCompanyId] });
      setShowProviderModal(false);
      setFetchedModels([]);
      setFetchModelsError(null);
      setProviderForm({ name: '', provider_type: 'api', api_vendor: 'openai', api_key: '', base_url: '', agent: '', model: '', custom_model: '' });
    },
  });

  const fetchModels = async () => {
    setIsFetchingModels(true);
    setFetchModelsError(null);
    try {
      const res = await rpcCall<{ models: { model: string; display_name: string }[]; source: string; error_message: string | null }>(
        'provider.models.fetch',
        {
          api_vendor: providerForm.api_vendor,
          api_key: providerForm.api_key,
          base_url: providerForm.base_url,
        },
      );
      setFetchedModels(res?.models ?? []);
      if (res.source === 'fallback' && res.error_message) setFetchModelsError(res.error_message);
      setProviderForm((f) => ({ ...f, model: '' }));
    } catch (e) {
      setFetchModelsError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsFetchingModels(false);
    }
  };

  const createBackendMutation = useMutation({
    mutationFn: () => rpcCall('backend.create', { company_id: currentCompanyId, name: backendForm.name.trim(), backend_type: backendForm.backend_type, workspace_root: backendForm.workspace_root.trim(), provider_id: activeProviderId ?? undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backend', currentCompanyId] });
      setShowBackendModal(false);
      setBackendForm({ name: '', backend_type: 'local_process', workspace_root: '' });
    },
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
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Backend</h3>
          <button
            onClick={() => setShowBackendModal(true)}
            className="flex items-center gap-1 px-2.5 py-1 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            <Plus size={12} /> 新建 Backend
          </button>
        </div>
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
                    <td className="px-4 py-2.5 text-gray-600">{b.backend_type ?? b.type}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={b.status} /></td>
                    <td className="px-4 py-2.5"><StatusBadge status={b.health_status ?? b.health} /></td>
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
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Provider</h3>
          <button
            onClick={() => setShowProviderModal(true)}
            className="flex items-center gap-1 px-2.5 py-1 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            <Plus size={12} /> 新建 Provider
          </button>
        </div>
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
                      <td className="px-4 py-2.5 text-gray-600">{p.provider_type ?? p.type}</td>
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
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </section>

      {showProviderModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[420px] shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">新建 Provider</h3>
              <button onClick={() => setShowProviderModal(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">名称</label>
                <input
                  value={providerForm.name}
                  onChange={(e) => setProviderForm({ ...providerForm, name: e.target.value })}
                  placeholder="如：opencode"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">类型</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setProviderForm({ ...providerForm, provider_type: 'api' })}
                    className={`flex-1 px-3 py-2 text-sm rounded-md border ${providerForm.provider_type === 'api' ? 'border-blue-400 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600'}`}
                  >
                    API Key 形式
                  </button>
                  <button
                    type="button"
                    onClick={() => setProviderForm({ ...providerForm, provider_type: 'cli' })}
                    className={`flex-1 px-3 py-2 text-sm rounded-md border ${providerForm.provider_type === 'cli' ? 'border-blue-400 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600'}`}
                  >
                    调用 Agent 形式
                  </button>
                </div>
              </div>

              {providerForm.provider_type === 'api' && (
                <>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">供应商</label>
                    <select
                      value={providerForm.api_vendor}
                      onChange={(e) => setProviderForm({ ...providerForm, api_vendor: e.target.value as typeof providerForm.api_vendor, model: '' })}
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                    >
                      <option value="openai">OpenAI</option>
                      <option value="deepseek">DeepSeek</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="third_party">第三方（OpenAI 兼容）</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">
                      {providerForm.api_vendor === 'deepseek' ? 'DeepSeek API Key'
                        : providerForm.api_vendor === 'anthropic' ? 'Anthropic API Key'
                          : providerForm.api_vendor === 'openai' ? 'OpenAI API Key'
                            : '第三方 API Key'}
                    </label>
                    <input
                      type="password"
                      value={providerForm.api_key}
                      onChange={(e) => setProviderForm({ ...providerForm, api_key: e.target.value })}
                      placeholder="API Key（用于实时查询可用模型）"
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">Base URL（可选，留空用供应商默认）</label>
                    <input
                      value={providerForm.base_url}
                      onChange={(e) => setProviderForm({ ...providerForm, base_url: e.target.value })}
                      placeholder={
                        providerForm.api_vendor === 'anthropic' ? 'https://api.anthropic.com/v1'
                          : providerForm.api_vendor === 'deepseek' ? 'https://api.deepseek.com'
                            : '如：https://api.openai.com/v1'
                      }
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-sm text-gray-600">模型</label>
                      <button
                        type="button"
                        onClick={fetchModels}
                        disabled={isFetchingModels}
                        className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-40"
                      >
                        {isFetchingModels ? '查询中...' : '查询可用模型'}
                      </button>
                    </div>
                    {fetchModelsError && (
                      <p className="text-xs text-amber-600 mb-1">查询失败，已用内置清单：{fetchModelsError}</p>
                    )}
                    <select
                      value={providerForm.model}
                      onChange={(e) => setProviderForm({ ...providerForm, model: e.target.value })}
                      disabled={fetchedModels.length === 0}
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                    >
                      <option value="">{fetchedModels.length === 0 ? '先填写 Key 并点“查询可用模型”' : '请选择模型'}</option>
                      {fetchedModels.map((m) => <option key={m.model} value={m.model}>{m.display_name}</option>)}
                      <option value="__custom__">自定义（手动输入）</option>
                    </select>
                  </div>
                  {providerForm.model === '__custom__' && (
                    <div>
                      <input
                        value={providerForm.custom_model}
                        onChange={(e) => setProviderForm({ ...providerForm, custom_model: e.target.value })}
                        placeholder="手动输入模型名"
                        className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                  )}
                </>
              )}

              {providerForm.provider_type === 'cli' && (
                <>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">Agent 工具</label>
                    <select
                      value={providerForm.agent}
                      onChange={(e) => setProviderForm({ ...providerForm, agent: e.target.value, model: '' })}
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                    >
                      <option value="">请选择 Agent</option>
                      {agents?.map((a) => <option key={a.agent_id} value={a.agent_id}>{a.display_name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">模型</label>
                    <select
                      value={providerForm.model}
                      onChange={(e) => setProviderForm({ ...providerForm, model: e.target.value })}
                      disabled={!providerForm.agent}
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                    >
                      <option value="">请选择模型</option>
                      {selectedAgent?.models.map((m) => <option key={m.model} value={m.model}>{m.display_name}</option>)}
                      {providerForm.agent !== 'cursor-cli' && <option value="__custom__">自定义（手动输入）</option>}
                    </select>
                  </div>
                  {providerForm.model === '__custom__' && (
                    <div>
                      <input
                        value={providerForm.custom_model}
                        onChange={(e) => setProviderForm({ ...providerForm, custom_model: e.target.value })}
                        placeholder="手动输入模型名"
                        className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowProviderModal(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => createProviderMutation.mutate()}
                disabled={
                  !providerForm.name.trim() ||
                  createProviderMutation.isPending ||
                  (providerForm.provider_type === 'api' && (!providerForm.model || (providerForm.model === '__custom__' && !providerForm.custom_model.trim()))) ||
                  (providerForm.provider_type === 'cli' && (!providerForm.agent || !modelValue)) ||
                  (providerForm.provider_type === 'cli' && providerForm.model === '__custom__' && !providerForm.custom_model.trim())
                }
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {createProviderMutation.isPending ? '创建中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showBackendModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">新建 Backend</h3>
              <button onClick={() => setShowBackendModal(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">名称</label>
                <input
                  value={backendForm.name}
                  onChange={(e) => setBackendForm({ ...backendForm, name: e.target.value })}
                  placeholder="如：opencode-local"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">类型</label>
                <select
                  value={backendForm.backend_type}
                  onChange={(e) => setBackendForm({ ...backendForm, backend_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400 h-[38px]"
                >
                  <option value="local_process">local_process</option>
                  <option value="openai">openai</option>
                  <option value="anthropic">anthropic</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Workspace 根目录（必填）</label>
                <input
                  value={backendForm.workspace_root}
                  onChange={(e) => setBackendForm({ ...backendForm, workspace_root: e.target.value })}
                  placeholder="如：/Users/ken/workspace/agent-runs"
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowBackendModal(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">取消</button>
              <button
                onClick={() => createBackendMutation.mutate()}
                disabled={!backendForm.name.trim() || !backendForm.workspace_root.trim() || createBackendMutation.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {createBackendMutation.isPending ? '创建中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
