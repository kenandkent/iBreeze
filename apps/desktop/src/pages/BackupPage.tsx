import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Typography, Table, Button, Tag, message } from 'antd';
import { invoke } from '@tauri-apps/api/core';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ColumnsType } from 'antd/es/table';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const { Title } = Typography;

interface BackupRecord {
  id: string;
  backup_type: string;
  status: string;
  sha256: string;
  created_at: string;
}

export default function BackupPage() {
  const { companyId } = useParams<{ companyId: string }>();
  useEffect(() => { logger.logPageInit('BackupPage'); }, []);

  const qc = useQueryClient();

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ['backups', companyId!],
    queryFn: async (): Promise<BackupRecord[]> => {
      logger.info('BackupPage', 'list_start');
      return invoke<BackupRecord[]>('rpc_request', { method: 'backup.list', params: { company_id: companyId! } });
    },
  });

  const createBackup = useMutation({
    mutationFn: async () => {
      logger.info('BackupPage', 'create_start');
      return invoke('rpc_request', { method: 'backup.create', params: { company_id: companyId!, backup_type: 'manual' } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backups'] });
      message.success('备份创建成功');
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('BackupPage', 'create_failed', msg);
    },
  });

  const columns: ColumnsType<BackupRecord> = [
    { title: '类型', dataIndex: 'backup_type', key: 'backup_type', render: (s: string) => <Tag>{s}</Tag> },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'completed' ? 'green' : 'default'}>{s}</Tag>,
    },
    { title: 'SHA-256', dataIndex: 'sha256', key: 'sha256', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: formatTime },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>备份管理</Title>
        <Button type="primary" onClick={() => { logger.logAction('BackupPage', 'create_backup'); createBackup.mutate(); }} loading={createBackup.isPending}>创建备份</Button>
      </div>
      <Table columns={columns} dataSource={backups} rowKey="id" loading={isLoading} />
    </div>
  );
}
