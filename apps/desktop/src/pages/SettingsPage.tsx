import { useState, useEffect } from 'react';
import { Card, Tabs, Typography, Form, Input, Button, Switch, Space } from 'antd';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function SettingsPage() {
  useEffect(() => { logger.logPageInit('SettingsPage'); }, []);

  const [activeTab, setActiveTab] = useState('general');

  const items = [
    {
      key: 'general',
      label: '通用设置',
      children: (
        <Form layout="vertical" style={{ maxWidth: 600 }}>
          <Form.Item label="语言">
            <Input defaultValue="zh-CN" disabled />
          </Form.Item>
          <Form.Item label="时区">
            <Input defaultValue="Asia/Shanghai" disabled />
          </Form.Item>
          <Form.Item label="自动备份">
            <Switch defaultChecked />
          </Form.Item>
          <Form.Item>
            <Button type="primary">保存设置</Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'security',
      label: '安全设置',
      children: (
        <Form layout="vertical" style={{ maxWidth: 600 }}>
          <Form.Item label="修改密码">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Input.Password placeholder="当前密码" />
              <Input.Password placeholder="新密码" />
              <Input.Password placeholder="确认新密码" />
            </Space>
          </Form.Item>
          <Form.Item>
            <Button type="primary">更新密码</Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'about',
      label: '关于',
      children: (
        <Space direction="vertical">
          <Title level={4}>iBreeze</Title>
          <p>AI 公司桌面应用</p>
          <p>版本: 1.0.0</p>
        </Space>
      ),
    },
  ];

  return (
    <Card>
      <Title level={3}>设置</Title>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
    </Card>
  );
}
