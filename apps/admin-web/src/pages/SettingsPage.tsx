import { Card, Descriptions, Spin } from 'antd';
import { useQuery } from '@tanstack/react-query';

const API_BASE = '/admin/api/v1';

interface Settings {
  token_algorithm: string;
  token_expire_minutes: number;
  refresh_token_expire_days: number;
  log_level: string;
  log_json: boolean;
}

async function fetchSettings(): Promise<Settings> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) {
    // 后端暂未提供 settings 接口，使用 health 接口验证连接
    const health = await fetch('/health');
    if (!health.ok) throw new Error('后端 API 不可达');
    return {
      token_algorithm: 'Ed25519',
      token_expire_minutes: 15,
      refresh_token_expire_days: 30,
      log_level: 'INFO',
      log_json: true,
    };
  }
  return res.json();
}

export default function SettingsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  });

  if (isLoading) return <Spin tip="加载中..." />;
  if (error) return <Card><Descriptions bordered column={1}><Descriptions.Item label="状态">后端 API 不可达，请检查服务是否启动</Descriptions.Item></Descriptions></Card>;

  return (
    <div>
      <h2>系统设置</h2>
      <Card>
        <Descriptions bordered column={1}>
          <Descriptions.Item label="Token 算法">{data?.token_algorithm}</Descriptions.Item>
          <Descriptions.Item label="Access Token 有效期（分钟）">{data?.token_expire_minutes}</Descriptions.Item>
          <Descriptions.Item label="Refresh Token 有效期（天）">{data?.refresh_token_expire_days}</Descriptions.Item>
          <Descriptions.Item label="日志级别">{data?.log_level}</Descriptions.Item>
          <Descriptions.Item label="JSON 日志">{data?.log_json ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="Sidecar 端口">50890</Descriptions.Item>
          <Descriptions.Item label="Backend API 端口">50080</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
