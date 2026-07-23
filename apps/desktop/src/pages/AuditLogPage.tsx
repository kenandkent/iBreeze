import { useState } from 'react';
import {
  Typography, DatePicker, Select, Button, Timeline, Tag, Space, Card,
} from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import type { AuditLogEntry } from '../types';
import { useListAuditLogs, useExportAuditLogs } from '../hooks/useAudit';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const eventTypeColor: Record<string, string> = {
  company_created: 'blue',
  company_updated: 'cyan',
  conversation_created: 'green',
  task_started: 'orange',
  task_completed: 'purple',
  agent_run_completed: 'green',
  agent_run_failed: 'red',
};

export default function AuditLogPage() {
  const [timeRange, setTimeRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [eventType, setEventType] = useState<string | undefined>(undefined);

  const startTime = timeRange?.[0]?.toISOString();
  const endTime = timeRange?.[1]?.toISOString();

  const { data: auditLogs, isLoading } = useListAuditLogs({
    start_time: startTime,
    end_time: endTime,
    event_type: eventType,
  });
  const exportMutation = useExportAuditLogs();

  const handleExport = async () => {
    const data = await exportMutation.mutateAsync({
      start_time: startTime,
      end_time: endTime,
      event_type: eventType,
    });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>审计日志</Title>

      {/* 筛选栏 */}
      <Card style={{ marginBottom: 24 }}>
        <Space wrap>
          <RangePicker
            showTime
            onChange={(values) => {
              if (values && values[0] && values[1]) {
                setTimeRange([values[0], values[1]]);
              } else {
                setTimeRange(null);
              }
            }}
          />
          <Select
            placeholder="事件类型"
            allowClear
            value={eventType}
            onChange={setEventType}
            style={{ width: 180 }}
          >
            <Select.Option value="company_created">创建企业</Select.Option>
            <Select.Option value="company_updated">更新企业</Select.Option>
            <Select.Option value="conversation_created">创建对话</Select.Option>
            <Select.Option value="task_started">任务开始</Select.Option>
            <Select.Option value="task_completed">任务完成</Select.Option>
            <Select.Option value="agent_run_completed">Agent 运行完成</Select.Option>
            <Select.Option value="agent_run_failed">Agent 运行失败</Select.Option>
          </Select>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={exportMutation.isPending}
          >
            导出 JSON
          </Button>
        </Space>
      </Card>

      {/* 时间线 */}
      {auditLogs && auditLogs.data.length > 0 ? (
        <Timeline
          items={auditLogs.data.map((log: AuditLogEntry) => ({
            color: log.event_type.includes('failed') ? 'red' : 'blue',
            children: (
              <div>
                <Space>
                  <Tag color={eventTypeColor[log.event_type] || 'default'}>{log.event_type}</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(log.created_at).toLocaleString('zh-CN')}
                  </Text>
                </Space>
                <div style={{ marginTop: 4 }}>
                  <Text>操作者: {log.actor_id}</Text>
                </div>
                <div>
                  <Text type="secondary">
                    资源: {log.resource_type} ({log.resource_id.slice(0, 8)}...)
                  </Text>
                </div>
                {log.detail && Object.keys(log.detail).length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      详情: {JSON.stringify(log.detail)}
                    </Text>
                  </div>
                )}
              </div>
            ),
          }))}
        />
      ) : (
        <Card>
          <Text type="secondary">{isLoading ? '加载中...' : '暂无审计日志'}</Text>
        </Card>
      )}
    </div>
  );
}
