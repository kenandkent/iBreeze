import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout as AntLayout, Menu, Typography, Switch, Space, Avatar, Dropdown } from 'antd';
import {
  DashboardOutlined,
  BankOutlined,
  MessageOutlined,
  BookOutlined,
  AppstoreOutlined,
  ApartmentOutlined,
  RobotOutlined,
  AuditOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useAppStore } from '../stores/appStore';
import { useAuthStore } from '../stores/authStore';

const { Sider, Header, Content } = AntLayout;
const { Text } = Typography;

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '总览' },
  { key: '/companies', icon: <BankOutlined />, label: '企业管理' },
  { key: '/conversations', icon: <MessageOutlined />, label: '对话管理' },
  { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
  { key: '/workspaces', icon: <AppstoreOutlined />, label: '工作区' },
  { key: '/orchestrations', icon: <ApartmentOutlined />, label: '编排管理' },
  { key: '/agents', icon: <RobotOutlined />, label: 'Agent 管理' },
  { key: '/audit-logs', icon: <AuditOutlined />, label: '审计日志' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar, theme, setTheme } = useAppStore();
  const { user, logout } = useAuthStore();

  const userMenuItems = [
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: () => { logout(); navigate('/login', { replace: true }); } },
  ];

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={sidebarCollapsed}
        onCollapse={toggleSidebar}
        theme="dark"
        width={220}
      >
        <div style={{ padding: '16px', textAlign: 'center' }}>
          <Text strong style={{ color: '#fff', fontSize: sidebarCollapsed ? 14 : 18 }}>
            {sidebarCollapsed ? 'iB' : 'iBreeze'}
          </Text>
          {!sidebarCollapsed && (
            <div><Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>AI Company Desktop</Text></div>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Space size={16}>
            <Space size={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>深色</Text>
              <Switch
                checked={theme === 'dark'}
                onChange={(checked) => setTheme(checked ? 'dark' : 'light')}
                size="small"
              />
            </Space>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} size="small" />
                <Text>{user?.display_name || user?.email || '用户'}</Text>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
