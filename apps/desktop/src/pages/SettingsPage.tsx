import { useState, useEffect } from 'react';
import { Card, Tabs, Typography, Form, Input, Button, Switch, Space, message } from 'antd';
import { invoke } from '@tauri-apps/api/core';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function SettingsPage() {
  useEffect(() => { logger.logPageInit('SettingsPage'); }, []);

  const [activeTab, setActiveTab] = useState('general');
  const [changingPwd, setChangingPwd] = useState(false);
  const [pwdForm] = Form.useForm();

  const handleSaveGeneral = async () => {
    logger.logAction('SettingsPage', 'save_general');
    message.success('设置已保存');
  };

  const handleChangePassword = async (values: { current_password: string; new_password: string; confirm_password: string }) => {
    if (values.new_password !== values.confirm_password) {
      message.error('两次输入的新密码不一致');
      return;
    }
    setChangingPwd(true);
    try {
      logger.info('SettingsPage', 'change_password_start');
      await invoke('rpc_request', {
        method: 'auth.changePassword',
        params: { current_password: values.current_password, new_password: values.new_password },
      });
      message.success('密码修改成功');
      pwdForm.resetFields();
    } catch (e) {
      const err = e as Record<string, unknown>;
      const msg = (err?.error as string) || (e instanceof Error ? e.message : '密码修改失败');
      logger.error('SettingsPage', 'change_password_failed', msg);
      message.error(msg);
    } finally {
      setChangingPwd(false);
    }
  };

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
            <Button type="primary" onClick={handleSaveGeneral}>保存设置</Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'security',
      label: '安全设置',
      children: (
        <Form form={pwdForm} layout="vertical" style={{ maxWidth: 600 }} onFinish={handleChangePassword}>
          <Form.Item label="当前密码" name="current_password" rules={[{ required: true, message: '请输入当前密码' }]}>
            <Input.Password placeholder="当前密码" />
          </Form.Item>
          <Form.Item label="新密码" name="new_password" rules={[{ required: true, message: '请输入新密码' }, { min: 8, message: '密码至少8位' }]}>
            <Input.Password placeholder="新密码" />
          </Form.Item>
          <Form.Item label="确认新密码" name="confirm_password" dependencies={['new_password']} rules={[
            { required: true, message: '请确认新密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                return Promise.reject(new Error('两次输入的密码不一致'));
              },
            }),
          ]}>
            <Input.Password placeholder="确认新密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={changingPwd}>更新密码</Button>
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
