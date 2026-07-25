import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Typography, Descriptions, Tag, Spin } from 'antd';
import { useGetCompanyTask } from '../hooks/useTask';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function TaskDetailPage() {
  useEffect(() => { logger.logPageInit('TaskDetailPage'); }, []);

  const { id } = useParams<{ id: string }>();
  const companyId = 'default';
  const { data: task, isLoading } = useGetCompanyTask(companyId, id || '');

  if (isLoading) return <Spin />;
  if (!task) return <Card>任务不存在</Card>;

  return (
    <Card>
      <Title level={3}>{task.title}</Title>
      <Descriptions bordered column={2}>
        <Descriptions.Item label="状态"><Tag>{task.status}</Tag></Descriptions.Item>
        <Descriptions.Item label="优先级">{task.priority}</Descriptions.Item>
        <Descriptions.Item label="描述" span={2}>{task.description}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatTime(task.created_at)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatTime(task.updated_at)}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
