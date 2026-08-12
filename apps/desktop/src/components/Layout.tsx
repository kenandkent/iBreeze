import { Outlet, useNavigate, useLocation, useParams } from 'react-router-dom';
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
  CloudUploadOutlined,
  CheckCircleOutlined,
  SafetyOutlined,
  ExperimentOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useAppStore } from '../stores/appStore';
import { useAuthStore } from '../stores/authStore';
import { logger } from '../utils/logger';

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
  { key: '/skills', icon: <ExperimentOutlined />, label: '技能管理' },
  { key: '/audit-logs', icon: <AuditOutlined />, label: '审计日志' },
  { key: '/reviews', icon: <CheckCircleOutlined />, label: '审查问题' },
  { key: '/approvals', icon: <SafetyOutlined />, label: '审批列表' },
  { key: '/backups', icon: <CloudUploadOutlined />, label: '备份管理' },
];

const companyScopedMenuKeys = new Set([
  '/dashboard', '/conversations', '/knowledge', '/workspaces', '/orchestrations',
  '/agents', '/skills', '/audit-logs', '/reviews', '/approvals', '/backups',
]);

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { companyId } = useParams<{ companyId?: string }>();
  const { sidebarCollapsed, toggleSidebar, theme, setTheme } = useAppStore();
  const { maskedIdentifier, closeProfile } = useAuthStore();

  const handleMenuClick = ({ key }: { key: string }) => {
    logger.logMenuClick(key);
    const target = companyId && companyScopedMenuKeys.has(key)
      ? `/companies/${companyId}${key}`
      : key;
    logger.logNavigation(location.pathname, target);
    navigate(target);
  };

  const handleThemeToggle = (checked: boolean) => {
    logger.info('Layout', 'theme_toggle', { theme: checked ? 'dark' : 'light' });
    setTheme(checked ? 'dark' : 'light');
  };

  const handleLogout = () => {
    logger.info('Layout', 'logout');
    closeProfile();
    navigate('/login', { replace: true });
  };

  const userMenuItems = [
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
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
          selectedKeys={[companyId && location.pathname.startsWith(`/companies/${companyId}`)
            ? location.pathname.slice(`/companies/${companyId}`.length) || '/dashboard'
            : location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>

      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Space size={16}>
            <Space size={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>深色</Text>
              <Switch
                checked={theme === 'dark'}
                onChange={handleThemeToggle}
                size="small"
              />
            </Space>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} size="small" />
                <Text>{maskedIdentifier || '用户'}</Text>
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
