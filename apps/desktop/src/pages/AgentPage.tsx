import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Row, Col, Tag, Typography, Button, Input, Space, Empty } from 'antd';
import { PlayCircleOutlined, PoweroffOutlined } from '@ant-design/icons';
import type { AgentInfo } from '../types';
import { useListAgents } from '../hooks/useAgent';
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
  useEffect(() => { logger.logPageInit('AgentPage'); }, []);

  const [messageInputs, setMessageInputs] = useState<Record<string, string>>({});
  const { data: agents, isLoading } = useListAgents(companyId!);

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
    </div>
  );
}
