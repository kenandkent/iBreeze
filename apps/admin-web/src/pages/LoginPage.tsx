import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { Form, Input, Button, Card, Alert, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { logger } from '../utils/logger';

export default function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      logger.info('LoginPage', 'login_start', { username: values.username });
      const res = await fetch('/admin/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const code = body.code || body.detail;
        logger.error('LoginPage', 'login_http_error', { username: values.username, status: res.status }, code);
        if (code === 'AUTH_PASSWORD_CHANGE_REQUIRED') {
          setError('首次登录需要修改密码');
          return;
        }
        throw new Error(body.detail || '登录失败');
      }
      const data = await res.json();
      if (data.data.pwd_change_required) {
        setError('首次登录需要修改密码');
        return;
      }
      login(data.data.access_token, data.data.user);
      logger.info('LoginPage', 'login_success', { username: values.username });
      message.success('登录成功');
      navigate('/agents', { replace: true });
    } catch (e) {
      const msg = e instanceof Error ? e.message : '用户名或密码错误';
      logger.error('LoginPage', 'login_failed', { username: values.username }, msg);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card title="iBreeze 管理后台" style={{ width: 400 }}>
        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}
        <Form onFinish={onFinish} autoComplete="off">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
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
