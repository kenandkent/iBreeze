import { useRef } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import api from '../../services/api';

interface Item { log_id: string; actor_id: string; action: string; resource_type: string; details: Record<string, unknown>; created_at: string; }

export default function Intervention() {
  const ref = useRef<ActionType>();
  const cols: ProColumns<Item>[] = [
    { title: '操作者', dataIndex: 'actor_id', width: 120 },
    { title: '操作', dataIndex: 'action', width: 200 },
    { title: '资源类型', dataIndex: 'resource_type', width: 120 },
    { title: '详情', dataIndex: 'details', ellipsis: true, render: (_, r) => JSON.stringify(r.details) },
    { title: '时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
  ];
  return (
    <ProTable<Item> headerTitle="人工干预" actionRef={ref} rowKey="log_id" columns={cols}
      request={async (p) => { const { data } = await api.get('/audit/interventions', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
      search={{ labelWidth: 'auto' }}
      pagination={{ defaultPageSize: 20 }}
    />
  );
}
