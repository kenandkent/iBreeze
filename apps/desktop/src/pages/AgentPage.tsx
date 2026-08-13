import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Card, Row, Col, Tag, Typography, Button, Input, Space, Empty } from 'antd';
import { PlayCircleOutlined, PoweroffOutlined } from '@ant-design/icons';
import type { AgentInfo } from '../types';
import { useListAgents } from '../hooks/useAgent';
import { useProfiles } from '../hooks/useRouting';
import { logger } from '../utils/logger';

const { Title, Text } = Typography;

const statusColor: Record<string, string> = {
  running: 'green',
  stopped: 'default',
  error: 'red',
};

const statusLabel: Record<string, string> = {
  running: '运行中',
  stopped: '已停止',
  error: '异常',
};

export default function AgentPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const navigate = useNavigate();
  useEffect(() => { logger.logPageInit('AgentPage'); }, []);

  const [messageInputs, setMessageInputs] = useState<Record<string, string>>({});
  const { data: agents, isLoading } = useListAgents(companyId!);
  const profiles = useProfiles(companyId!);

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>Agent 管理</Title>

      {(!agents || agents.length === 0) && !isLoading ? (
        <Empty description="暂无 Agent" />
      ) : (
        <Row gutter={[16, 16]}>
          {agents?.map((agent: AgentInfo) => (
            <Col xs={24} sm={12} lg={8} key={agent.id}>
              <Card
                title={
                  <Space>
                    <Text strong>{agent.name}</Text>
                    <Tag color={statusColor[agent.status]}>{statusLabel[agent.status] || agent.status}</Tag>
                  </Space>
                }
                extra={
                  <Space>
                    <Button
                      type="primary"
                      size="small"
                      icon={<PlayCircleOutlined />}
                      disabled={agent.status === 'running'}
                    >
                      运行
                    </Button>
                    <Button
                      danger
                      size="small"
                      icon={<PoweroffOutlined />}
                      disabled={agent.status === 'stopped'}
                    >
                      停止
                    </Button>
                  </Space>
                }
              >
                <Text type="secondary">类型: {agent.agent_type}</Text>
                {agent.description && (
                  <div style={{ marginTop: 8 }}>
                    <Text>{agent.description}</Text>
                  </div>
                )}
                <div style={{ marginTop: 12 }}>
                  <Input
                    placeholder="输入消息..."
                    value={messageInputs[agent.id] || ''}
                    onChange={(e) =>
                      setMessageInputs((prev) => ({ ...prev, [agent.id]: e.target.value }))
                    }
                  />
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}
      <Card title="职员模型底座" style={{ marginTop: 24 }} loading={profiles.isLoading}>
        <TableLikeProfiles
          profiles={profiles.data?.profiles ?? []}
          onOpen={(profileId) => navigate(`/companies/${companyId}/profiles/${profileId}/routing`)}
        />
      </Card>
    </div>
  );
}

function TableLikeProfiles({ profiles, onOpen }: { profiles: Array<{ profile_id: string; display_name: string; profile_type: 'agent_cli' | 'api_model'; current_version_status: string; updated_at: string }>; onOpen: (profileId: string) => void }) {
  return <div style={{ display: 'grid', gap: 8 }}>{profiles.length === 0 ? <Text type="secondary">暂无模型底座</Text> : profiles.map(profile => <Space key={profile.profile_id} style={{ justifyContent: 'space-between' }}>
    <Text>{profile.display_name}</Text>
    <Tag>{profile.profile_type === 'api_model' ? 'API Model' : 'CLI Agent'}</Tag>
    <Tag>{profile.current_version_status}</Tag>
    <Button size="small" onClick={() => onOpen(profile.profile_id)}>{profile.profile_type === 'api_model' ? '配置路由' : '查看说明'}</Button>
  </Space>)}</div>;
}
