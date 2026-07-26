import { Typography } from 'antd';
import { logger } from '../utils/logger';
import { useEffect } from 'react';

const { Title, Text } = Typography;

export default function SkillsPage() {
  useEffect(() => { logger.logPageInit('SkillsPage'); }, []);

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>技能管理</Title>
      <Text type="secondary">技能管理功能已移至企业设置中。请在选定企业后，在企业管理页面中配置技能。</Text>
    </div>
  );
}
