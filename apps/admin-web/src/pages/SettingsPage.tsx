import { Card, Descriptions } from 'antd';

const MOCK_SETTINGS = {
  token_algorithm: 'Ed25519',
  token_expire_minutes: 15,
  refresh_token_expire_days: 30,
  log_level: 'info',
  log_json: true,
  sidecar_port: 8765,
};

export default function SettingsPage() {
  return (
    <div>
      <h2>系统设置</h2>
      <Card>
        <Descriptions bordered column={1}>
          <Descriptions.Item label="Token 算法">{MOCK_SETTINGS.token_algorithm}</Descriptions.Item>
          <Descriptions.Item label="Access Token 有效期（分钟）">{MOCK_SETTINGS.token_expire_minutes}</Descriptions.Item>
          <Descriptions.Item label="Refresh Token 有效期（天）">{MOCK_SETTINGS.refresh_token_expire_days}</Descriptions.Item>
          <Descriptions.Item label="日志级别">{MOCK_SETTINGS.log_level}</Descriptions.Item>
          <Descriptions.Item label="JSON 日志">{MOCK_SETTINGS.log_json ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="Sidecar 端口">{MOCK_SETTINGS.sidecar_port}</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
