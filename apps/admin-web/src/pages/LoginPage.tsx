import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { Form, Input, Button, Card, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { logger } from '../utils/logger';

export default function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      logger.info('LoginPage', 'login_start', { email: values.email });
      const res = await fetch('/admin/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        logger.error('LoginPage', 'login_http_error', { email: values.email, status: res.status, detail: body.detail });
        throw new Error(body.detail || '登录失败');
      }
      const data = await res.json();
      login(data.data.access_token, data.data.user);
      logger.info('LoginPage', 'login_success', { email: values.email });
      message.success('登录成功');
    } catch (e) {
      const msg = e instanceof Error ? e.message : '邮箱或密码错误';
      logger.error('LoginPage', 'login_failed', { email: values.email }, msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card title="iBreeze 管理后台" style={{ width: 400 }}>
        <Form onFinish={onFinish} autoComplete="off">
          <Form.Item name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input prefix={<UserOutlined />} placeholder="邮箱" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
