import { useRef, useState } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Button, Tag, message, Popconfirm, Modal, Form, Input } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../../services/api';

interface Item { knowledge_id: string; title: string; category: string; status: string; governance_confirmed: number; created_at: string; }

export default function KnowledgeList() {
  const ref = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [form] = Form.useForm();
  const cols: ProColumns<Item>[] = [
    { title: '标题', dataIndex: 'title', width: 250 },
    { title: '分类', dataIndex: 'category', width: 120 },
    { title: '状态', dataIndex: 'status', width: 80, render: (_, r) => <Tag color={r.status === 'active' ? 'success' : 'default'}>{r.status}</Tag> },
    { title: '治理确认', dataIndex: 'governance_confirmed', width: 100, render: (_, r) => <Tag color={r.governance_confirmed === 1 ? 'success' : r.governance_confirmed === -1 ? 'error' : 'default'}>{r.governance_confirmed === 1 ? '已确认' : r.governance_confirmed === -1 ? '已拒绝' : '待确认'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 200,
      render: (_, r) => [
        <a key="e" onClick={() => { setEditing(r); form.setFieldsValue({ title: r.title, category: r.category }); setModalOpen(true); }}>编辑</a>,
        r.governance_confirmed === 0 && <a key="c" onClick={() => confirm(r.knowledge_id, 1)}>确认</a>,
        r.governance_confirmed === 0 && <a key="r" onClick={() => confirm(r.knowledge_id, -1)}>拒绝</a>,
        <Popconfirm key="d" title="确定删除?" onConfirm={() => del(r.knowledge_id)}><a>删除</a></Popconfirm>,
      ].filter(Boolean),
    },
  ];
  const confirm = async (id: string, v: number) => { try { await api.post(`/knowledge/documents/${id}/${v === 1 ? 'confirm' : 'reject'}`); message.success('操作成功'); ref.current?.reload(); } catch { message.error('操作失败'); } };
  const del = async (id: string) => { try { await api.delete(`/knowledge/documents/${id}`); message.success('已删除'); ref.current?.reload(); } catch { message.error('删除失败'); } };
  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await api.put(`/knowledge/documents/${editing.knowledge_id}`, values);
        message.success('更新成功');
      } else {
        await api.post('/knowledge/documents', { company_id: 'default', ...values });
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
      <ProTable<Item> headerTitle="知识库" actionRef={ref} rowKey="knowledge_id" columns={cols}
        request={async (p) => { const { data } = await api.get('/knowledge/documents', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>新建文档</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title={editing ? '编辑文档' : '新建文档'} open={modalOpen} onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields(); }} onOk={handleSubmit} destroyOnClose>
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="category" label="分类"><Input /></Form.Item>
          <Form.Item name="content" label="内容"><Input.TextArea rows={4} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
