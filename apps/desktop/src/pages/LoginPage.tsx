import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, Alert } from 'antd';
import { MailOutlined, LockOutlined } from '@ant-design/icons';
import { invoke } from '@tauri-apps/api/core';
import { useAuthStore } from '../stores/authStore';
import type { AuthResult } from '../types';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);

  const handleSubmit = async (values: { email: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      logger.info('LoginPage', 'login_start', { email: values.email });
      const result = await invoke<AuthResult>('login', {
        email: values.email,
        password: values.password,
      });
      logger.info('LoginPage', 'login_success', { email: values.email });
      login(result.access_token, result.refresh_token, {
        id: 'current',
        user_type: result.user_type as 'admin' | 'app_user',
        email: values.email,
        display_name: values.email,
        status: 'active',
      });
      navigate('/dashboard', { replace: true });
    } catch (e) {
      const err = e as Record<string, unknown>;
      const msg = (err?.error as string) || (e instanceof Error ? e.message : '登录失败');
      logger.error('LoginPage', 'login_failed', { email: values.email }, msg);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>iBreeze</Title>
          <Typography.Text type="secondary">AI Company Desktop</Typography.Text>
        </div>

        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

        <Form layout="vertical" onFinish={handleSubmit} autoComplete="off">
          <Form.Item name="email" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
            <Input prefix={<MailOutlined />} placeholder="邮箱" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              登录
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Link to="/register">还没有账号？注册</Link>
        </div>
      </Card>
    </div>
  );
}
