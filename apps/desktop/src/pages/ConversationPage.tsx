import { useState } from 'react';
import {
  Layout, List, Button, Input, Tag, Typography, Space, Empty, Card,
} from 'antd';
import { PlusOutlined, SendOutlined, SearchOutlined } from '@ant-design/icons';

import {
  useListConversations,
  useListMessages,
  useAddMessage,
  useArchiveConversation,
} from '../hooks/useConversation';

const { Sider, Content } = Layout;
const { Text } = Typography;

const messageRoleColor: Record<string, string> = {
  user: '#1677ff',
  assistant: '#f5f5f5',
  system: '#f5f5f5',
  tool: '#f6ffed',
};

export default function ConversationPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');

  const { data: conversations } = useListConversations();
  const { data: messages } = useListMessages(selectedId ?? '');
  const addMessage = useAddMessage();
  const archiveMutation = useArchiveConversation();

  const selectedConversation = conversations?.find((c) => c.id === selectedId);
  const isArchived = selectedConversation?.status === 'archived';

  const handleSend = async () => {
    if (!inputValue.trim() || !selectedId) return;
    await addMessage.mutateAsync({ conversationId: selectedId, content: inputValue, role: 'user' });
    setInputValue('');
  };

  const handleArchive = async (id: string) => {
    await archiveMutation.mutateAsync(id);
    if (selectedId === id) setSelectedId(null);
  };

  return (
    <Layout style={{ minHeight: 'calc(100vh - 64px)' }}>
      <Sider width={320} style={{ background: '#fff', borderRight: '1px solid #f0f0f0' }}>
        <div style={{ padding: 16 }}>
          <Space style={{ width: '100%', marginBottom: 12 }}>
            <Input prefix={<SearchOutlined />} placeholder="搜索对话" style={{ flex: 1 }} />
            <Button type="primary" icon={<PlusOutlined />} />
          </Space>
          <List
            dataSource={conversations}
            renderItem={(item) => (
              <List.Item
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                style={{
                  cursor: 'pointer',
                  background: selectedId === item.id ? '#e6f4ff' : undefined,
                  padding: '8px 12px',
                  borderRadius: 6,
                }}
                actions={[
                  <Button
                    key="archive"
                    size="small"
                    type="text"
                    onClick={(e) => { e.stopPropagation(); handleArchive(item.id); }}
                  >
                    归档
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text ellipsis style={{ maxWidth: 160 }}>{item.title || '新对话'}</Text>
                      {item.status === 'archived' && <Tag>已归档</Tag>}
                    </Space>
                  }
                  description={
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {new Date(item.created_at).toLocaleString('zh-CN')}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      </Sider>

      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        {!selectedId ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty description="选择一个对话" />
          </div>
        ) : (
          <>
            {/* 消息区域 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              {isArchived && (
                <div style={{ textAlign: 'center', marginBottom: 16 }}>
                  <Tag color="warning">已归档 - 对话已归档，无法发送新消息</Tag>
                </div>
              )}
              {messages?.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    display: 'flex',
                    justifyContent: msg.role === 'user' ? 'flex-end' : msg.role === 'system' ? 'center' : 'flex-start',
                    marginBottom: 12,
                  }}
                >
                  {msg.role === 'system' ? (
                    <Tag>{msg.content}</Tag>
                  ) : (
                    <Card
                      size="small"
                      style={{
                        maxWidth: '70%',
                        background: messageRoleColor[msg.role] || '#f5f5f5',
                        borderColor: msg.role === 'user' ? '#1677ff' : '#f0f0f0',
                      }}
                      styles={{ body: { padding: '8px 12px' } }}
                    >
                      <Text>{msg.content}</Text>
                    </Card>
                  )}
                </div>
              ))}
            </div>

            {/* 输入区域 */}
            <div style={{ padding: 16, borderTop: '1px solid #f0f0f0' }}>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={isArchived ? '对话已归档' : '输入消息...'}
                  disabled={isArchived || addMessage.isPending}
                  onPressEnter={handleSend}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleSend}
                  loading={addMessage.isPending}
                  disabled={isArchived}
                >
                  发送
                </Button>
              </Space.Compact>
            </div>
          </>
        )}
      </Content>
    </Layout>
  );
}
