import { Card, Form, Input, Select, Button, Descriptions, Tag, message, Space } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useEmergencyDisable, useLatestEmergencyDisable } from '../hooks/useReleases';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const RESOURCE_TYPES = ['agents', 'models', 'providers', 'skills'];

export default function EmergencyPage() {
  const emergencyDisable = useEmergencyDisable();
  const { data: latestDisable, isLoading: latestLoading } = useLatestEmergencyDisable();
  const [form] = Form.useForm();

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      await emergencyDisable.mutateAsync({
        resource_type: values.resource_type,
        resource_id: values.resource_id,
        resource_version: values.resource_version,
        action: values.action,
        reason: values.reason,
        code: values.code,
      });
      message.success('紧急禁用已执行');
      form.resetFields();
    } catch (error) {
      logger.error('EmergencyPage', 'emergency_disable_failed', undefined, error);
      message.error('紧急禁用失败');
    }
  };

  return (
    <div>
      <h2>紧急禁用</h2>
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Card title="执行紧急禁用" variant="outlined">
          <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
            <Form.Item name="resource_type" label="资源类型" rules={[{ required: true }]}>
              <Select placeholder="选择资源类型">
                {RESOURCE_TYPES.map((t) => (
                  <Select.Option key={t} value={t}>{t}</Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="resource_id" label="资源 ID" rules={[{ required: true, message: '请输入资源 ID' }]}>
              <Input placeholder="资源的 UUID" />
            </Form.Item>
            <Form.Item name="resource_version" label="资源版本">
              <Input placeholder="可选，指定版本号" />
            </Form.Item>
            <Form.Item name="action" label="操作" rules={[{ required: true }]} initialValue="disable">
              <Select>
                <Select.Option value="disable">禁用</Select.Option>
                <Select.Option value="rollback">回滚</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="reason" label="原因" rules={[{ required: true, message: '请输入禁用原因' }]}>
              <Input.TextArea rows={2} placeholder="紧急禁用原因" />
            </Form.Item>
            <Form.Item name="code" label="紧急确认码" rules={[{ required: true, message: '输入 EMERGENCY 确认' }]}>
              <Input placeholder="输入 EMERGENCY 确认" />
            </Form.Item>
            <Button
              type="primary"
              danger
              icon={<ExclamationCircleOutlined />}
              onClick={handleSubmit}
              loading={emergencyDisable.isPending}
            >
              执行紧急禁用
            </Button>
          </Form>
        </Card>

        <Card title="最近禁用记录" variant="outlined" loading={latestLoading}>
          {latestDisable ? (
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="ID">{latestDisable.id}</Descriptions.Item>
              <Descriptions.Item label="序号">{latestDisable.sequence}</Descriptions.Item>
              <Descriptions.Item label="已禁用的资源类型" span={2}>
                {latestDisable.resource_type ? (
                  <Tag color="red">{latestDisable.resource_type}</Tag>
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="已禁用的资源 ID" span={2}>
                {latestDisable.resource_id || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatTime(latestDisable.created_at)}</Descriptions.Item>
            </Descriptions>
          ) : (
            <span>暂无紧急禁用记录</span>
          )}
        </Card>
      </Space>
    </div>
  );
}
