import React from 'react';
import { Typography, Space, Badge, Tooltip, Select, Tag } from 'antd';
import { 
  MenuFoldOutlined, 
  MenuUnfoldOutlined,
  WifiOutlined,
  ApiOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import { useSystemStore } from '../../stores/useSystemStore';
import { useSensorStore } from '../../stores/useSensorStore';
import { getStatusColor, getStatusText } from '../../utils/statusHelpers';

const { Title } = Typography;

export const Header: React.FC = () => {
  const { connection, ui, toggleSidebar } = useSystemStore();
  const { robotIds, activeRobotId, setActiveRobot } = useSensorStore();

  return (
    <div
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        height: '64px',
        padding: '0 16px',
        background: '#001529',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
      }}
    >
      <Space align="center">
        <div
          onClick={toggleSidebar}
          style={{
            fontSize: '18px',
            color: 'white',
            cursor: 'pointer',
            padding: '4px',
          }}
        >
          {ui.sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
        <Title level={4} style={{ margin: 0, color: '#00ff88' }}>
          ROS远程监控系统 v2.0 (多机)
        </Title>
      </Space>

      <Space size="middle">
        {/* 机器人选择器 */}
        <Select
          value={activeRobotId}
          onChange={(val) => setActiveRobot(val)}
          style={{ minWidth: 160 }}
          size="small"
          placeholder={robotIds.length > 0 ? "选择机器人" : "无在线机器人"}
          disabled={robotIds.length === 0}
          options={[
            { value: null, label: '全部机器人' },
            ...robotIds.map(id => ({ value: id, label: id })),
          ]}
        />

        {/* 机器人在线数 */}
        <Tag color={robotIds.length > 0 ? "processing" : "default"} style={{ margin: 0 }}>
          {robotIds.length} 在线
        </Tag>

        {/* WebSocket连接状态 */}
        <Tooltip title={`WebSocket: ${getStatusText(connection.websocket)}`}>
          <Badge 
            color={getStatusColor(connection.websocket)}
            dot
          >
            <WifiOutlined style={{ color: 'white', fontSize: '16px' }} />
          </Badge>
        </Tooltip>

        {/* API连接状态 */}
        <Tooltip title={`API: ${getStatusText(connection.api)}`}>
          <Badge 
            color={getStatusColor(connection.api)}
            dot
          >
            <ApiOutlined style={{ color: 'white', fontSize: '16px' }} />
          </Badge>
        </Tooltip>

        {/* 延迟显示 */}
        <Tooltip title={`延迟: ${connection.latency}ms`}>
          <Space style={{ color: 'white' }}>
            <ClockCircleOutlined />
            <span>{connection.latency}ms</span>
          </Space>
        </Tooltip>
      </Space>
    </div>
  );
};
