import { useRef, useState } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Button, Tag, message, Popconfirm, Modal, Form, Input } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../../services/api';

interface ApprovalType { type_id: string; name: string; description: string; version: string; created_at: string; }

export default function Governance() {
  const ref = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ApprovalType | null>(null);
  const [form] = Form.useForm();
  const cols: ProColumns<ApprovalType>[] = [
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '版本', dataIndex: 'version', width: 80 },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 120,
      render: (_, r) => [
        <a key="e" onClick={() => { setEditing(r); form.setFieldsValue({ name: r.name, description: r.description }); setModalOpen(true); }}>编辑</a>,
        <Popconfirm key="d" title="确定删除?" onConfirm={() => del(r.type_id)}><a>删除</a></Popconfirm>,
      ],
    },
  ];
  const del = async (id: string) => { try { await api.delete(`/governance/approval-types/${id}`); message.success('已删除'); ref.current?.reload(); } catch { message.error('删除失败'); } };
  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await api.put(`/governance/approval-types/${editing.type_id}`, values);
        message.success('更新成功');
      } else {
        await api.post('/governance/approval-types', { company_id: 'default', ...values });
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      form.resetFields();
      ref.current?.reload();
    } catch { message.error(editing ? '更新失败' : '创建失败'); }
  };
  return (
    <>
      <ProTable<ApprovalType> headerTitle="审批类型" actionRef={ref} rowKey="type_id" columns={cols}
        request={async (p) => { try { const { data } = await api.get('/governance/approval-types', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; } catch { return { data: [], success: true, total: 0 }; } }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>新建审批类型</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title={editing ? '编辑审批类型' : '新建审批类型'} open={modalOpen} onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields(); }} onOk={handleSubmit} destroyOnClose>
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
