import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Typography, Table, Tag, Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReviewIssue } from '../types';
import { useListReviewIssues, useResolveReviewIssue } from '../hooks/useReview';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const { Title } = Typography;

const severityColor: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'blue',
  low: 'default',
};

export default function ReviewPage() {
  const { companyId } = useParams<{ companyId: string }>();
  useEffect(() => { logger.logPageInit('ReviewPage'); }, []);

  const artifactId = 'default';
  const { data: issues = [], isLoading } = useListReviewIssues(companyId!, artifactId);
  const resolveIssue = useResolveReviewIssue();

  const handleResolve = async (issueId: string) => {
    try {
      logger.info('ReviewPage', 'resolve_start', { issueId });
      await resolveIssue.mutateAsync({ company_id: companyId!, issue_id: issueId });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('ReviewPage', 'resolve_failed', msg, { issueId });
    }
  };

  const columns: ColumnsType<ReviewIssue> = [
    {
      title: '严重度',
      dataIndex: 'severity',
      key: 'severity',
      render: (s: string) => <Tag color={severityColor[s] || 'default'}>{s}</Tag>,
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '文件', dataIndex: 'file_path', key: 'file_path', ellipsis: true },
    { title: '行号', dataIndex: 'line_number', key: 'line_number' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'open' ? 'orange' : 'green'}>{s}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: formatTime },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) =>
        record.status === 'open' ? (
          <Button size="small" onClick={() => { logger.logAction('ReviewPage', 'resolve_issue'); handleResolve(record.id); }}>解决</Button>
        ) : null,
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>审查问题</Title>
      <Table columns={columns} dataSource={issues} rowKey="id" loading={isLoading} />
    </div>
  );
}
