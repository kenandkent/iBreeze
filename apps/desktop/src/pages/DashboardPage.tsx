import { Card, Col, Row, Statistic, Timeline, Button, Typography, Space } from 'antd';
import {
  BankOutlined,
  MessageOutlined,
  BookOutlined,
  AppstoreOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useListCompanies } from '../hooks/useCompany';
import { useListConversations } from '../hooks/useConversation';
import { useListKnowledgeEntries } from '../hooks/useKnowledge';
import { useListWorkspaces } from '../hooks/useWorkspace';
import { useListAuditLogs } from '../hooks/useAudit';

const { Title, Text } = Typography;

export default function DashboardPage() {
  const navigate = useNavigate();

  const { data: companies } = useListCompanies();
  const { data: conversations } = useListConversations('');
  const { data: knowledge } = useListKnowledgeEntries();
  const { data: workspaces } = useListWorkspaces();
  const { data: auditLogs } = useListAuditLogs({ limit: 10 });

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>总览仪表盘</Title>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="企业数" value={companies?.total ?? 0} prefix={<BankOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="对话数" value={conversations?.length ?? 0} prefix={<MessageOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="知识条目" value={knowledge?.total ?? 0} prefix={<BookOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="工作区" value={workspaces?.length ?? 0} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* 快捷操作 */}
      <Card title="快捷操作" style={{ marginBottom: 24 }}>
        <Space wrap>
          <Button icon={<PlusOutlined />} onClick={() => navigate('/conversations')}>
            新建对话
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => navigate('/companies')}>
            新建企业
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => navigate('/knowledge')}>
            新建知识条目
          </Button>
        </Space>
      </Card>

      {/* 最近活动 */}
      <Card title="最近活动">
        {auditLogs && auditLogs.data.length > 0 ? (
          <Timeline
            items={auditLogs.data.map((log) => ({
              children: (
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(log.created_at).toLocaleString('zh-CN')}
                  </Text>
                  <br />
                  <Text>
                    {log.event_type} - {log.resource_type}({log.resource_id.slice(0, 8)})
                  </Text>
                </div>
              ),
            }))}
          />
        ) : (
          <Text type="secondary">暂无活动记录</Text>
        )}
      </Card>
    </div>
  );
}
