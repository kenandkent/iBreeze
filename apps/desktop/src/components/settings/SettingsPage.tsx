import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rpcCall } from '../../services/rpcClient';
import { useAppStore } from '../../stores/appStore';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { X } from 'lucide-react';

type PolicyKind = 'company' | 'knowledgePolicy' | 'notification' | 'securityPolicy' | 'workspacePolicy';

const POLICY_META: Record<PolicyKind, { key: string; title: string; method: string; needAgreed: boolean; notice?: string }> = {
  company: { key: 'company', title: '公司设置', method: 'settings.company', needAgreed: false },
  knowledgePolicy: { key: 'knowledgePolicy', title: '知识策略', method: 'settings.knowledgePolicy', needAgreed: true, notice: '云端知识策略更新需显式同意。' },
  notification: { key: 'notification', title: '通知设置', method: 'settings.notification', needAgreed: false },
  securityPolicy: { key: 'securityPolicy', title: '安全策略', method: 'settings.securityPolicy', needAgreed: false },
  workspacePolicy: { key: 'workspacePolicy', title: '工作区策略', method: 'settings.workspacePolicy', needAgreed: false },
};

type PolicyData = Record<string, unknown> & { version?: number };

function PolicySection({ companyId, kind }: { companyId: string; kind: PolicyKind }) {
  const meta = POLICY_META[kind];
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const [agreed, setAgreed] = useState(false);

  const { data, isLoading, error } = useQuery<PolicyData>({
    queryKey: ['settings', companyId, meta.key],
    queryFn: () => rpcCall<PolicyData>(`${meta.method}.get`, { company_id: companyId }),
    enabled: !!companyId,
  });

  const update = useMutation({
    mutationFn: () => {
      let updates: Record<string, unknown>;
      try {
        updates = JSON.parse(text);
      } catch {
        throw new Error('JSON 格式不正确');
      }
      const params: Record<string, unknown> = {
        company_id: companyId,
        expected_version: data?.version,
        updates,
      };
      if (meta.needAgreed) params.agreed = agreed;
      return rpcCall(`${meta.method}.update`, params);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', companyId, meta.key] });
      setEditing(false);
      setAgreed(false);
    },
    onError: (err: Error) => alert('更新失败: ' + err.message),
  });

  function openEdit() {
    const { version, exists, ...rest } = data ?? {};
    setText(JSON.stringify(rest, null, 2));
    setEditing(true);
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-700">{meta.title}</h3>
        <button
          onClick={openEdit}
          disabled={isLoading || !companyId}
          className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-40"
        >
          编辑
        </button>
      </div>
      {!companyId ? (
        <p className="text-sm text-gray-400">请先在左侧选择公司</p>
      ) : isLoading ? (
        <LoadingSpinner />
      ) : error ? (
        <p className="text-sm text-red-500">加载失败: {error.message}</p>
      ) : (
        <pre className="text-xs text-gray-600 whitespace-pre-wrap break-all bg-gray-50 rounded p-2 max-h-60 overflow-auto">
          {JSON.stringify(data ?? {}, null, 2)}
        </pre>
      )}

      {editing && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setEditing(false)}>
          <div className="bg-white rounded-lg p-6 w-[480px] max-h-[80vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-medium">编辑{meta.title}</h3>
              <button onClick={() => setEditing(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            {meta.notice && <p className="text-xs text-amber-600 mb-3">{meta.notice}</p>}
            <label className="block text-sm text-gray-600 mb-1">更新内容（JSON）</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={10}
              className="w-full px-3 py-2 border border-gray-200 rounded-md text-xs font-mono focus:outline-none focus:border-blue-400"
              autoFocus
            />
            {meta.needAgreed && (
              <label className="flex items-center gap-2 mt-3 text-sm text-gray-600">
                <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
                我已阅读并同意云端策略
              </label>
            )}
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-md">取消</button>
              <button
                onClick={() => update.mutate()}
                disabled={update.isPending || (meta.needAgreed && !agreed)}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {update.isPending ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function SettingsPage() {
  const [health, setHealth] = useState<string>('检查中...');
  const [version] = useState('0.1.0');
  const companyId = useAppStore((s) => s.currentCompanyId);

  useEffect(() => {
    rpcCall<{ status: string }>('sys.health')
      .then(() => setHealth('正常'))
      .catch(() => setHealth('未连接'));
  }, []);

  const policyKinds: PolicyKind[] = ['company', 'knowledgePolicy', 'notification', 'securityPolicy', 'workspacePolicy'];

  return (
    <div className="p-6 max-w-3xl">
      <h2 className="text-lg font-semibold text-gray-800 mb-6">设置</h2>

      <div className="space-y-4">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">系统信息</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">版本</span>
              <span className="text-gray-800">v{version}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Sidecar 状态</span>
              <span className={health === '正常' ? 'text-green-600' : 'text-gray-800'}>{health}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">平台</span>
              <span className="text-gray-800">macOS Apple Silicon</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">关于</h3>
          <p className="text-sm text-gray-600">
            iBreeze 是一个本地 AI 组织运行平台，支持创建虚拟公司、分配 AI 员工、管理知识库和执行任务工作流。
          </p>
        </div>

        {policyKinds.map((kind) => (
          <PolicySection key={kind} companyId={companyId ?? ''} kind={kind} />
        ))}
      </div>
    </div>
  );
}
