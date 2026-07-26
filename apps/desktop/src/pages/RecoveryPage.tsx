import { useState, useEffect } from 'react';
import { Card, Typography, Button, Space, Result, message } from 'antd';
import { WarningOutlined, ReloadOutlined, RollbackOutlined, ExportOutlined } from '@ant-design/icons';
import { invoke } from '@tauri-apps/api/core';
import { logger } from '../utils/logger';

const { Title, Text } = Typography;

export default function RecoveryPage() {
  const [verifying, setVerifying] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [verified, setVerified] = useState<boolean | null>(null);

  useEffect(() => { logger.logPageInit('RecoveryPage'); checkOnMount(); }, []);

  const checkOnMount = async () => {
    try {
      const ok = await invoke<boolean>('updater_verify_launch');
      setVerified(ok);
      if (ok) {
        logger.info('RecoveryPage', 'verify_ok');
      }
    } catch (e) {
      setVerified(false);
      logger.error('RecoveryPage', 'verify_on_mount_failed', String(e));
    }
  };

  const handleRetryVerify = async () => {
    setVerifying(true);
    try {
      logger.info('RecoveryPage', 'retry_verify');
      const ok = await invoke<boolean>('updater_verify_launch');
      setVerified(ok);
      if (ok) {
        message.success('验证通过，即将返回系统');
        setTimeout(() => window.location.replace('/login'), 1500);
      } else {
        message.warning('验证仍未通过');
      }
    } catch (e) {
      message.error('验证执行失败');
      logger.error('RecoveryPage', 'retry_verify_failed', String(e));
    } finally {
      setVerifying(false);
    }
  };

  const handleRestoreStable = async () => {
    setRestoring(true);
    try {
      logger.info('RecoveryPage', 'restore_stable');
      await invoke<boolean>('updater_restore_stable');
      message.success('已恢复至稳定版本，即将重启');
      setTimeout(() => window.location.replace('/login'), 1500);
    } catch (e) {
      message.error('恢复失败');
      logger.error('RecoveryPage', 'restore_stable_failed', String(e));
    } finally {
      setRestoring(false);
    }
  };

  const handleExportDiagnostics = async () => {
    try {
      logger.info('RecoveryPage', 'export_diagnostics');
      const path = await invoke<string>('diagnostics_export');
      message.success(`诊断信息已导出至: ${path}`);
    } catch (e) {
      message.error('导出失败');
      logger.error('RecoveryPage', 'export_diagnostics_failed', String(e));
    }
  };

  if (verified === null) {
    return (
      <Card style={{ maxWidth: 600, margin: '120px auto', textAlign: 'center' }}>
        <Title level={3}>正在检查更新状态...</Title>
      </Card>
    );
  }

  if (verified) {
    return (
      <Card style={{ maxWidth: 600, margin: '120px auto', textAlign: 'center' }}>
        <Result
          status="success"
          title="系统运行正常"
          subTitle="当前版本已验证通过"
          extra={
            <Button type="primary" onClick={() => window.location.replace('/login')}>
              进入系统
            </Button>
          }
        />
      </Card>
    );
  }

  return (
    <Card style={{ maxWidth: 600, margin: '120px auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%', textAlign: 'center' }}>
        <WarningOutlined style={{ fontSize: 48, color: '#faad14' }} />
        <Title level={3}>更新恢复</Title>
        <Text type="secondary">
          系统检测到上次更新未正确完成，请选择以下恢复操作：
        </Text>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Button
            block
            size="large"
            icon={<ReloadOutlined />}
            loading={verifying}
            onClick={handleRetryVerify}
          >
            重试验证
          </Button>
          <Button
            block
            size="large"
            icon={<RollbackOutlined />}
            loading={restoring}
            onClick={handleRestoreStable}
          >
            恢复稳定版本
          </Button>
          <Button
            block
            size="large"
            icon={<ExportOutlined />}
            onClick={handleExportDiagnostics}
          >
            导出诊断
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
