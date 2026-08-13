import { useState, useEffect } from 'react';
import { Card, Tabs, Typography, Form, Input, Button, Switch, Space, message, Table, Tag } from 'antd';
import { invoke } from '@tauri-apps/api/core';
import { createRpcRequest } from '../shared/rpcClient';
import { logger } from '../utils/logger';
import CredentialSettings from '../components/CredentialSettings';
import { useClearExpiredHealth, useDeploymentHealth } from '../hooks/useRouting';
import { formatNumber, formatTime } from '../utils/formatters';

const { Title } = Typography;

function AboutTab() {
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<{
    available: boolean;
    current: string;
    latest: string;
  } | null>(null);

  const handleCheck = async () => {
    setChecking(true);
    try {
      logger.info('SettingsPage', 'update_check');
      const result = await invoke<{
        available: boolean;
        current_version: string;
        latest_version: string;
      }>('updater_check');
      setUpdateInfo({
        available: result.available,
        current: result.current_version,
        latest: result.latest_version,
      });
      if (!result.available) {
        message.info('已是最新版本');
      }
    } catch (e) {
      message.error('检查更新失败');
      logger.error('SettingsPage', 'update_check_failed', String(e));
    } finally {
      setChecking(false);
    }
  };

  const handleInstall = async () => {
    if (!updateInfo?.available) return;
    setInstalling(true);
    try {
      logger.info('SettingsPage', 'update_install');
      const result = await invoke<{ success: boolean; new_version: string }>('updater_install');
      if (result.success) {
        message.success(`更新 ${result.new_version} 已安装，请重启应用`);
        setUpdateInfo(prev => prev ? { ...prev, available: false, latest: result.new_version } : null);
      }
    } catch (e) {
      message.error('安装更新失败');
      logger.error('SettingsPage', 'update_install_failed', String(e));
    } finally {
      setInstalling(false);
    }
  };

  useEffect(() => { handleCheck(); }, []);

  return (
    <Space direction="vertical" size="middle">
      <Title level={4}>iBreeze</Title>
      <p>AI 公司桌面应用</p>
      {updateInfo && (
        <>
          <p>当前版本: {updateInfo.current}</p>
          {updateInfo.available && <p>最新版本: {updateInfo.latest}</p>}
        </>
      )}
      <Space>
        <Button onClick={handleCheck} loading={checking}>检查更新</Button>
        {updateInfo?.available && (
          <Button type="primary" onClick={handleInstall} loading={installing}>
            安装更新 ({updateInfo.latest})
          </Button>
        )}
      </Space>
    </Space>
  );
}

function RoutingHealthTab() {
  const companyId = window.location.pathname.match(/\/companies\/([^/]+)/)?.[1] ?? '';
  const health = useDeploymentHealth(companyId);
  const clearExpired = useClearExpiredHealth(companyId);
  return <Space direction="vertical" style={{ width: '100%' }}>
    <Typography.Paragraph type="secondary">仅展示当前公司的 Deployment Health；active bench 和 credential_invalid 不能在界面中绕过。</Typography.Paragraph>
    <Button loading={clearExpired.isPending} disabled={!companyId} onClick={() => clearExpired.mutate()}>清除已过期健康记录</Button>
    <Table loading={health.isLoading} rowKey={(row) => `${row.provider_release_id}:${row.model_binding_id}:${row.credential_slot}`} dataSource={health.data?.items ?? []} pagination={false} columns={[{ title: 'Provider', dataIndex: 'provider_release_id' }, { title: 'Model Binding', dataIndex: 'model_binding_id' }, { title: 'Credential Slot', dataIndex: 'credential_slot' }, { title: '状态', dataIndex: 'availability_state', render: (value: string) => <Tag color={value === 'ready' ? 'green' : 'red'}>{value}</Tag> }, { title: 'Strike', dataIndex: 'consecutive_strikes', render: (value: number) => formatNumber(value) }, { title: 'Bench 截止', dataIndex: 'benched_until', render: (value: string | null) => formatTime(value) }, { title: '最后失败', dataIndex: 'last_failure_kind' }, { title: '最后成功', dataIndex: 'last_success_at', render: (value: string | null) => formatTime(value) }]} />
  </Space>;
}

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
      await createRpcRequest('auth.changePassword', {
        current_password: values.current_password,
        new_password: values.new_password,
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
      key: 'credentials',
      label: 'Provider 凭据',
      children: <CredentialSettings />,
    },
    {
      key: 'routing-health',
      label: '路由健康',
      children: <RoutingHealthTab />,
    },
    {
      key: 'about',
      label: '关于',
      children: <AboutTab />,
    },
  ];

  return (
    <Card>
      <Title level={3}>设置</Title>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
    </Card>
  );
}
