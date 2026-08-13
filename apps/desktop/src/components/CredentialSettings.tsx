import { useState } from 'react';
import { Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useCatalogModels, useCredentials } from '../hooks/useRouting';

const { Text } = Typography;

export default function CredentialSettings() {
  const { data, isLoading, create, updateSecret, probe, remove } = useCredentials();
  const catalog = useCatalogModels();
  const [createOpen, setCreateOpen] = useState(false);
  const [updateTarget, setUpdateTarget] = useState<{ ref: string; version: number } | null>(null);
  const [form] = Form.useForm();
  const [secretForm] = Form.useForm();
  const clearSecret = (target: ReturnType<typeof Form.useForm>[0]) => target.resetFields(['secret']);
  const submitCreate = async (values: { label: string; provider_release_id: string; auth_type: 'bearer' | 'x_api_key'; secret: string }) => {
    try { await create.mutateAsync(values); message.success('Credential 已保存，需 Probe 后使用'); setCreateOpen(false); form.resetFields(); } catch { message.error('Credential 保存失败'); } finally { clearSecret(form); }
  };
  const submitUpdate = async (values: { secret: string }) => {
    if (!updateTarget) return;
    try { await updateSecret.mutateAsync({ credential_ref: updateTarget.ref, expected_metadata_version: updateTarget.version, secret: values.secret }); message.success('Secret 已更新，请重新 Probe'); setUpdateTarget(null); } catch { message.error('Secret 更新失败'); } finally { clearSecret(secretForm); }
  };
  const items = data?.items ?? [];
  return <Card title="Provider Credentials" extra={<Button type="primary" onClick={() => setCreateOpen(true)}>新增 Credential</Button>}>
    <Table rowKey="credential_ref" loading={isLoading} dataSource={items} pagination={false} columns={[
      { title: '名称', dataIndex: 'label' },
      { title: 'Provider', dataIndex: 'provider_release_id', render: (value: string) => <Text code>{value.slice(-8)}</Text> },
      { title: '状态', dataIndex: 'state', render: (value: string) => <Tag color={value === 'ready' ? 'green' : value === 'unverified' ? 'orange' : 'default'}>{value}</Tag> },
      { title: '凭据', dataIndex: 'credential_ref', render: (value: string) => <Text code>{value.slice(-8)}</Text> },
      { title: '操作', render: (_: unknown, row: (typeof items)[number]) => <Space>
        <Button size="small" disabled={row.state !== 'unverified' && row.state !== 'ready'} loading={probe.isPending} onClick={() => probe.mutate({ credential_ref: row.credential_ref, expected_metadata_version: row.metadata_version })}>Probe</Button>
        <Button size="small" onClick={() => setUpdateTarget({ ref: row.credential_ref, version: row.metadata_version })} disabled={row.state === 'creating' || row.state === 'updating' || row.state === 'deleting'}>更新 Secret</Button>
        <Button size="small" danger disabled={row.state === 'creating' || row.state === 'updating' || row.state === 'deleting'} onClick={() => remove.mutate({ credential_ref: row.credential_ref, expected_metadata_version: row.metadata_version })}>删除</Button>
      </Space> },
    ]} />
    <Modal title="新增 Credential" open={createOpen} onCancel={() => { setCreateOpen(false); clearSecret(form); }} onOk={() => form.submit()} confirmLoading={create.isPending} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={submitCreate}>
        <Form.Item name="label" label="名称" rules={[{ required: true, min: 1, max: 100 }]}><Input /></Form.Item>
        <Form.Item name="provider_release_id" label="Provider / Model" rules={[{ required: true }]}>
          <Select
            loading={catalog.isLoading}
            showSearch
            optionFilterProp="label"
            placeholder="仅可选择已签名 Catalog 中的 Provider"
            options={Array.from(new Map((catalog.data?.models ?? []).map(model => [model.provider_release_id, model])).values()).map(model => ({
              value: model.provider_release_id,
              label: `${model.provider} · ${model.name}${model.routing_enabled ? '' : '（仅 fixed 兼容）'}`,
            }))}
          />
        </Form.Item>
        <Form.Item name="auth_type" label="认证类型" initialValue="bearer" rules={[{ required: true }]}><Select options={[{ value: 'bearer', label: 'Bearer' }, { value: 'x_api_key', label: 'X API Key' }]} /></Form.Item>
        <Form.Item name="secret" label="Secret" rules={[{ required: true, min: 1 }]}><Input.Password autoComplete="new-password" /></Form.Item>
      </Form>
    </Modal>
    <Modal title="更新 Secret" open={Boolean(updateTarget)} onCancel={() => { setUpdateTarget(null); clearSecret(secretForm); }} onOk={() => secretForm.submit()} confirmLoading={updateSecret.isPending} destroyOnClose>
      <Form form={secretForm} layout="vertical" onFinish={submitUpdate}><Form.Item name="secret" label="新 Secret" rules={[{ required: true, min: 1 }]}><Input.Password autoComplete="new-password" /></Form.Item></Form>
    </Modal>
  </Card>;
}
