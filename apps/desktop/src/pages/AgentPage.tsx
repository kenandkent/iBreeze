import { useState } from 'react';
import { Card, Row, Col, Tag, Typography, Button, Input, Space, Empty } from 'antd';
import { PlayCircleOutlined, PoweroffOutlined, SendOutlined } from '@ant-design/icons';
import type { AgentInfo } from '../types';
import { useListAgents, useRunAgent, useStopAgent } from '../hooks/useAgent';

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
  const [messageInputs, setMessageInputs] = useState<Record<string, string>>({});
  const { data: agents, isLoading } = useListAgents();
  const runMutation = useRunAgent();
  const stopMutation = useStopAgent();

  const handleRun = async (agentId: string) => {
    const msg = messageInputs[agentId];
    if (!msg?.trim()) return;
    await runMutation.mutateAsync({ agent_id: agentId, message: msg });
    setMessageInputs((prev) => ({ ...prev, [agentId]: '' }));
  };

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
                      onClick={() => handleRun(agent.id)}
                    >
                      运行
                    </Button>
                    <Button
                      danger
                      size="small"
                      icon={<PoweroffOutlined />}
                      disabled={agent.status === 'stopped'}
                      loading={stopMutation.isPending}
                      onClick={() => stopMutation.mutateAsync(agent.id)}
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
                  <Space.Compact style={{ width: '100%' }}>
                    <Input
                      placeholder="输入消息..."
                      value={messageInputs[agent.id] || ''}
                      onChange={(e) =>
                        setMessageInputs((prev) => ({ ...prev, [agent.id]: e.target.value }))
                      }
                      onPressEnter={() => handleRun(agent.id)}
                    />
                    <Button icon={<SendOutlined />} onClick={() => handleRun(agent.id)} />
                  </Space.Compact>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
