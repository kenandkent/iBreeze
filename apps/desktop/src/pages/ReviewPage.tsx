import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Empty, Typography, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReviewIssue } from '../types';
import { useListReviewIssues } from '../hooks/useReview';
import { logger } from '../utils/logger';

const { Title } = Typography;

const severityColor: Record<string, string> = {
  blocker: 'red',
  high: 'orange',
  medium: 'blue',
  low: 'default',
};

export default function ReviewPage() {
  const { companyId, reviewId } = useParams<{ companyId: string; reviewId?: string }>();
  useEffect(() => { logger.logPageInit('ReviewPage'); }, []);

  const { data: issues = [], isLoading } = useListReviewIssues(companyId ?? '', reviewId ?? '');

  if (!reviewId) {
    return (
      <Card>
        <Title level={4}>审查问题</Title>
        <Empty description="请从任务证据链打开具体 Review" />
      </Card>
    );
  }

  const columns: ColumnsType<ReviewIssue> = [
    {
      title: '严重度',
      dataIndex: 'severity',
      key: 'severity',
      render: (s: string) => <Tag color={severityColor[s] || 'default'}>{s}</Tag>,
    },
    { title: '类别', dataIndex: 'category', key: 'category' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '状态', dataIndex: 'state', key: 'state',
      render: (s: string) => <Tag color={s === 'open' || s === 'fixing' ? 'orange' : 'green'}>{s}</Tag>,
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>审查问题</Title>
      <Table columns={columns} dataSource={issues} rowKey="issue_id" loading={isLoading} />
    </div>
  );
}
