import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { Form, Input, Button, Card, Alert, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { getDeviceId } from '../utils/deviceId';
import { apiLogin, ApiError } from '../utils/apiClient';
import { logger } from '../utils/logger';

export default function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const onFinish = async (values: { identifier: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      const deviceId = getDeviceId();
      logger.info('LoginPage', 'login_start', { identifier: values.identifier });
      const session = await apiLogin(values.identifier, values.password, deviceId);
      if (session.pwd_change_required) {
        logger.error('LoginPage', 'pwd_change_required', { identifier: values.identifier });
        setError('首次登录需要修改密码');
        return;
      }
      login(session.access_token, session.user);
      logger.info('LoginPage', 'login_success', { identifier: values.identifier });
      message.success('登录成功');
      navigate('/agents', { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'AUTH_PASSWORD_CHANGE_REQUIRED') {
        setError('首次登录需要修改密码');
        return;
      }
      const msg = e instanceof Error ? e.message : '用户名或密码错误';
      logger.error('LoginPage', 'login_failed', { identifier: values.identifier }, msg);
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
          <Form.Item name="identifier" rules={[{ required: true, message: '请输入用户名/邮箱/手机' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名/邮箱/手机" />
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
