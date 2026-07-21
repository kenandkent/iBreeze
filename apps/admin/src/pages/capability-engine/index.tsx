import { useEffect, useState } from 'react';
import { Card, Descriptions, Tag, Alert, Spin } from 'antd';
import api from '../../services/api';

export default function CapabilityEngine() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get('/health')
      .then(({ data }) => { setHealth(data); setLoading(false); })
      .catch(() => { setError('Admin Backend 不可达'); setLoading(false); });
  }, []);

  return (
    <Card title="能力引擎">
      {loading && <Spin />}
      {error && <Alert type="warning" message={error} showIcon />}
      {health && (
        <Descriptions bordered column={1}>
          <Descriptions.Item label="Admin Backend">
            <Tag color="success">{health.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Engine 模式">
            <Tag color="processing">Local Sidecar（通过 Admin Backend 查询）</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="能力加载来源">
            Admin Backend → Config Puller → Sidecar（UPSERT 同步）
          </Descriptions.Item>
          <Descriptions.Item label="说明">
            能力引擎运行在 Sidecar 进程中，通过 ConfigPuller 从 Admin Backend 拉取 Capability / Skill / Prompt 配置。
            此页面仅展示 Admin Backend 健康状态，引擎运行时状态请查看 Sidecar sys.health。
          </Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
}
