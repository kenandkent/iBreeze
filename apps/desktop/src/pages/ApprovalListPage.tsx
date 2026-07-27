import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Typography, Table, Tag, Button, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const { Title } = Typography;

interface ApprovalRecord {
  id: string;
  type: string;
  status: string;
  requester: string;
  created_at: string;
}

export default function ApprovalListPage() {
  const { companyId } = useParams<{ companyId: string }>();
  useEffect(() => { logger.logPageInit('ApprovalListPage'); }, []);

  const queryClient = useQueryClient();
  const { data: approvals = [], isLoading } = useQuery<ApprovalRecord[]>({
    queryKey: ['approvals'],
    queryFn: () => invoke('rpc_request', { method: 'approval.listPending', params: {} }),
  });

  const resolveMutation = useMutation({
    mutationFn: (id: string) =>
      invoke('rpc_request', {
        method: 'approval.resolve',
        params: { approval_id: id, decision: 'approved', company_id: companyId! },
        idempotencyKey: crypto.randomUUID(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) =>
      invoke('rpc_request', {
        method: 'approval.resolve',
        params: { approval_id: id, decision: 'rejected', company_id: companyId! },
        idempotencyKey: crypto.randomUUID(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
    },
  });

  const handleResolve = async (id: string) => {
    try {
      logger.info('ApprovalListPage', 'resolve_start', { id });
      await resolveMutation.mutateAsync(id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('ApprovalListPage', 'resolve_failed', msg, { id });
    }
  };

  const handleReject = async (id: string) => {
    try {
      logger.info('ApprovalListPage', 'reject_start', { id });
      await rejectMutation.mutateAsync(id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('ApprovalListPage', 'reject_failed', msg, { id });
    }
  };

  const columns: ColumnsType<ApprovalRecord> = [
    { title: '类型', dataIndex: 'type', key: 'type' },
    { title: '申请人', dataIndex: 'requester', key: 'requester' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'pending' ? 'orange' : s === 'approved' ? 'green' : 'red'}>{s}</Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: formatTime },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) =>
        record.status === 'pending' ? (
          <Space>
            <Button size="small" type="primary" onClick={() => { logger.logAction('ApprovalListPage', 'approve'); handleResolve(record.id); }}>
              批准
            </Button>
            <Button size="small" danger onClick={() => { logger.logAction('ApprovalListPage', 'reject'); handleReject(record.id); }}>
              拒绝
            </Button>
          </Space>
        ) : null,
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>审批列表</Title>
      <Table columns={columns} dataSource={approvals} rowKey="id" loading={isLoading} />
    </div>
  );
}
