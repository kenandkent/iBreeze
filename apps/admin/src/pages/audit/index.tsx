import { useRef } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Tag } from 'antd';
import api from '../../services/api';

interface Log { log_id: string; audit_type: string; actor_id: string; action: string; resource_type: string; created_at: string; }

export default function AuditLog() {
  const ref = useRef<ActionType>();
  const cols: ProColumns<Log>[] = [
    { title: '类型', dataIndex: 'audit_type', width: 100, render: (_, r) => <Tag>{r.audit_type}</Tag> },
    { title: '操作者', dataIndex: 'actor_id', width: 120 },
    { title: '操作', dataIndex: 'action', width: 200 },
    { title: '资源类型', dataIndex: 'resource_type', width: 120 },
    { title: '时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
  ];
  return (
    <ProTable<Log> headerTitle="审计日志" actionRef={ref} rowKey="log_id" columns={cols}
      request={async (p) => { const { data } = await api.get('/audit/logs', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
      search={{ labelWidth: 'auto' }}
      pagination={{ defaultPageSize: 20 }}
    />
  );
}
