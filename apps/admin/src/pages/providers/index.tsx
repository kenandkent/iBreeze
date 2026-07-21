import { useRef, useState } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Button, Tabs, Tag, message, Modal, Form, Input, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../../services/api';

interface Provider { provider_id: string; name: string; provider_type: string; status: string; created_at: string; }
interface Backend { backend_id: string; name: string; backend_type: string; status: string; created_at: string; }
const bsc: Record<string, string> = { disabled: 'default', enabled: 'success', draining: 'processing', archived: 'default' };

function ProviderTab() {
  const ref = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const transition = async (id: string, act: string) => { try { await api.post(`/providers/${id}/${act}`); message.success('操作成功'); ref.current?.reload(); } catch { message.error('操作失败'); } };
  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      await api.post('/providers', values);
      message.success('创建成功');
      setModalOpen(false);
      form.resetFields();
      ref.current?.reload();
    } catch { message.error('创建失败'); }
  };
  const cols: ProColumns<Provider>[] = [
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '类型', dataIndex: 'provider_type', width: 120 },
    { title: '状态', dataIndex: 'status', width: 100, render: (_, r) => <Tag color={r.status === 'enabled' ? 'success' : 'default'}>{r.status}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 200,
      render: (_, r) => [
        r.status === 'disabled' && <a key="e" onClick={() => transition(r.provider_id, 'enable')}>启用</a>,
        r.status === 'enabled' && <a key="d" onClick={() => transition(r.provider_id, 'disable')}>禁用</a>,
        <a key="v" onClick={() => transition(r.provider_id, 'validate')}>验证</a>,
      ].filter(Boolean),
    },
  ];
  return (
    <>
      <ProTable<Provider> headerTitle="Providers" actionRef={ref} rowKey="provider_id" columns={cols}
        request={async (p) => { const { data } = await api.get('/providers', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>新建 Provider</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title="新建 Provider" open={modalOpen} onCancel={() => { setModalOpen(false); form.resetFields(); }} onOk={handleSubmit} destroyOnClose>
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="provider_type" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'openai', label: 'OpenAI' }, { value: 'anthropic', label: 'Anthropic' }, { value: 'custom', label: 'Custom' }]} />
          </Form.Item>
          <Form.Item name="api_base" label="API Base"><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function BackendTab() {
  const ref = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const transition = async (id: string, act: string) => { try { await api.post(`/backends/${id}/${act}`); message.success('操作成功'); ref.current?.reload(); } catch { message.error('操作失败'); } };
  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      await api.post('/backends', values);
      message.success('创建成功');
      setModalOpen(false);
      form.resetFields();
      ref.current?.reload();
    } catch { message.error('创建失败'); }
  };
  const cols: ProColumns<Backend>[] = [
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '类型', dataIndex: 'backend_type', width: 120 },
    { title: '状态', dataIndex: 'status', width: 100, render: (_, r) => <Tag color={bsc[r.status]}>{r.status}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 250,
      render: (_, r) => [
        r.status === 'disabled' && <a key="e" onClick={() => transition(r.backend_id, 'enable')}>启用</a>,
        r.status === 'enabled' && <a key="d" onClick={() => transition(r.backend_id, 'drain')}>排空</a>,
        r.status === 'enabled' && <a key="s" onClick={() => transition(r.backend_id, 'set-default')}>设为默认</a>,
        r.status !== 'archived' && <a key="a" onClick={() => transition(r.backend_id, 'archive')}>归档</a>,
      ].filter(Boolean),
    },
  ];
  return (
    <>
      <ProTable<Backend> headerTitle="Backends" actionRef={ref} rowKey="backend_id" columns={cols}
        request={async (p) => { const { data } = await api.get('/backends', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>新建 Backend</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title="新建 Backend" open={modalOpen} onCancel={() => { setModalOpen(false); form.resetFields(); }} onOk={handleSubmit} destroyOnClose>
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="backend_type" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'openai', label: 'OpenAI' }, { value: 'anthropic', label: 'Anthropic' }, { value: 'custom', label: 'Custom' }]} />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL"><Input /></Form.Item>
          <Form.Item name="provider_id" label="Provider ID"><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}

export default function ProviderBackend() {
  const [tab, setTab] = useState('providers');
  return (
    <Tabs activeKey={tab} onChange={setTab} items={[
      { key: 'providers', label: 'Providers', children: <ProviderTab /> },
      { key: 'backends', label: 'Backends', children: <BackendTab /> },
    ]} />
  );
}
