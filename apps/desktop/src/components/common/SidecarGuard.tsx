import { useEffect, useState, type ReactNode } from 'react';
import { checkSidecarHealth } from '../../services/rpcClient';

interface Props {
  children: ReactNode;
}

export function SidecarGuard({ children }: Props) {
  const [status, setStatus] = useState<'checking' | 'ok' | 'error'>('checking');

  useEffect(() => {
    let cancelled = false;
    async function check() {
      const ok = await checkSidecarHealth();
      if (!cancelled) setStatus(ok ? 'ok' : 'error');
    }
    check();
    const timer = setInterval(check, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  if (status === 'checking') {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4" />
          <p className="text-sm text-gray-500">正在连接 Sidecar 服务...</p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">🔌</div>
          <h2 className="text-lg font-semibold text-gray-800 mb-2">Sidecar 服务未运行</h2>
          <p className="text-sm text-gray-500 mb-4">
            应用需要 Sidecar 后端服务才能正常工作。请确保以下条件满足：
          </p>
          <ul className="text-sm text-gray-500 text-left mb-6 space-y-1">
            <li>• 已安装 <code className="bg-gray-100 px-1 rounded">uv</code>（Python 包管理器）</li>
            <li>• Sidecar 源码在可访问的路径下</li>
            <li>• 环境变量 <code className="bg-gray-100 px-1 rounded">IBREEZE_SIDECAR_DIR</code> 已设置（可选）</li>
          </ul>
          <button
            onClick={() => setStatus('checking')}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
          >
            重新连接
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
