import { useEffect, useState } from 'react';
import { rpcCall } from '../../services/rpcClient';

export function SettingsPage() {
  const [health, setHealth] = useState<string>('检查中...');
  const [version] = useState('0.1.0');

  useEffect(() => {
    rpcCall<{ status: string }>('sys.health')
      .then(() => setHealth('正常'))
      .catch(() => setHealth('未连接'));
  }, []);

  return (
    <div className="p-6 max-w-2xl">
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
      </div>
    </div>
  );
}
