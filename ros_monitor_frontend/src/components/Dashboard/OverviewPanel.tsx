import React from 'react';
import { Card, Row, Col, Badge, Space, Tag, Typography, Statistic, Divider } from 'antd';
import {
  RobotOutlined,
  CameraOutlined,
  RadarChartOutlined,
  AimOutlined,
  WifiOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { useSensorStore } from '../../stores/useSensorStore';
import { useSystemStore } from '../../stores/useSystemStore';
import { getRobotColor } from '../../utils/constants';

const { Title, Text } = Typography;

interface RobotCardProps {
  robotId: string;
  index: number;
}

const RobotCard: React.FC<RobotCardProps> = ({ robotId, index }) => {
  const { robotData } = useSensorStore();
  const { robotConnections, robotTraffic } = useSystemStore();

  const state = robotData[robotId];
  const conn = robotConnections[robotId];
  const traffic = robotTraffic[robotId]; // 流量信息

  // 如果没有状态数据，说明刚上线还没收到数据
  if (!state) {
    return (
      <Card
        size="small"
        style={{ borderLeft: `4px solid ${getRobotColor(index)}`, opacity: 0.6 }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>{robotId}</Text>
          <Tag color="processing">等待数据中...</Tag>
        </Space>
      </Card>
    );
  }

  const { camera, lidar, gnss, slam } = state;
  const allSensors = [
    { key: 'camera', label: '相机', connected: camera.status.connected, icon: <CameraOutlined /> },
    { key: 'lidar', label: 'LiDAR', connected: lidar.status.connected, icon: <RadarChartOutlined /> },
    { key: 'gnss', label: 'GNSS', connected: gnss.status.connected, icon: <AimOutlined /> },
    { key: 'slam', label: 'SLAM', connected: slam.status.connected, icon: <AppstoreOutlined /> },
  ];
  // 只显示在线的传感器 —— 有什么传感器在线就显示什么标签
  const activeSensors = allSensors.filter(s => s.connected);

  const onlineCount = activeSensors.length;
  const lastUpdate = Math.max(
    camera.status.lastUpdate,
    lidar.status.lastUpdate,
    gnss.status.lastUpdate,
    slam.status.lastUpdate
  );
  const secondsAgo = lastUpdate > 0 ? Math.round((Date.now() - lastUpdate) / 1000) : -1;

  return (
    <Card
      size="small"
      style={{
        borderLeft: `4px solid ${getRobotColor(index)}`,
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      }}
      bodyStyle={{ padding: '12px 16px' }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="small">
        {/* 头部：名称 + 连接状态 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <RobotOutlined style={{ color: getRobotColor(index), fontSize: '18px' }} />
            <Text strong style={{ fontSize: '16px' }}>{robotId}</Text>
          </Space>
          <Badge
            status={conn?.ros ? 'success' : 'default'}
            text={conn?.ros ? '在线' : '离线'}
          />
        </div>

        <Divider style={{ margin: '8px 0' }} />

        {/* 传感器在线情况 —— 只显示在线传感器 */}
        <Row gutter={[8, 8]}>
          {activeSensors.length > 0 ? (
            activeSensors.map((sensor) => (
              <Col key={sensor.key}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    background: '#f6ffed',
                    border: '1px solid #b7eb8f',
                  }}
                >
                  <CheckCircleOutlined style={{ color: '#52c41a', fontSize: '12px' }} />
                  <span style={{ fontSize: '12px', color: '#389e0d' }}>
                    {sensor.label}
                  </span>
                </div>
              </Col>
            ))
          ) : (
            <Col span={24}>
              <Text type="secondary" style={{ fontSize: '12px' }}>无在线传感器</Text>
            </Col>
          )}
        </Row>

        {/* 统计信息 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
          <Tag color={onlineCount > 0 ? "blue" : "default"}>
            {onlineCount} 传感器在线
          </Tag>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {secondsAgo >= 0 ? `${secondsAgo}s 前更新` : '无数据'}
          </Text>
        </div>

        {/* 流量监控 */}
        {traffic && (
          <div style={{
            marginTop: '8px',
            padding: '6px 10px',
            background: '#fafafa',
            borderRadius: '4px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <Text type="secondary" style={{ fontSize: '11px' }}>
              📊 {traffic.total_kb.toFixed(1)} KB
            </Text>
            <Text
              style={{
                fontSize: '11px',
                color: traffic.rate_kbps > 50 ? '#ff4d4f' : traffic.rate_kbps > 10 ? '#faad14' : '#52c41a',
                fontWeight: 'bold',
              }}
            >
              {traffic.rate_kbps.toFixed(1)} KB/s
            </Text>
          </div>
        )}
      </Space>
    </Card>
  );
};

export const OverviewPanel: React.FC = () => {
  const { robotIds, robotData } = useSensorStore();
  const { connection, robotConnections } = useSystemStore();

  const totalRobots = robotIds.length;
  const onlineRobots = robotIds.filter(id => robotConnections[id]?.ros).length;
  const totalSensors = robotIds.reduce((count, id) => {
    const state = robotData[id];
    if (!state) return count;
    return count + [
      state.camera.status.connected,
      state.lidar.status.connected,
      state.gnss.status.connected,
      state.slam.status.connected,
    ].filter(Boolean).length;
  }, 0);
  // totalSensors 就是当前在线传感器数，不用再算一遍

  return (
    <div style={{ width: '100%' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', textAlign: 'center' }}>
        <Title level={2} style={{ color: '#1890ff', marginBottom: '12px' }}>
          <AppstoreOutlined style={{ marginRight: '12px' }} />
          总体概况
        </Title>
        <Text type="secondary" style={{ fontSize: '16px' }}>
          同时查看所有在线机器人的状态和传感器信息
        </Text>
      </div>

      {/* 总体统计 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={12} sm={6}>
          <Card style={{ textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <Statistic
              title={<Space><WifiOutlined /> 在线机器人</Space>}
              value={onlineRobots}
              suffix={`/ ${totalRobots}`}
              valueStyle={{ color: '#1890ff', fontSize: '28px' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <Statistic
              title={<Space><ThunderboltOutlined /> 传感器在线</Space>}
              value={totalSensors}
              suffix={`/ ${totalRobots * 4}`}
              valueStyle={{ color: '#52c41a', fontSize: '28px' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <Statistic
              title={<Space><ApiOutlined /> WebSocket</Space>}
              value={connection.websocket ? '已连接' : '未连接'}
              valueStyle={{ color: connection.websocket ? '#52c41a' : '#ff4d4f', fontSize: '24px' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <Statistic
              title={<Space><ClockCircleOutlined /> 系统状态</Space>}
              value={connection.websocket && connection.api ? '正常' : '异常'}
              valueStyle={{ color: connection.websocket && connection.api ? '#52c41a' : '#ff4d4f', fontSize: '24px' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 机器人卡片列表 */}
      <Title level={4} style={{ marginBottom: '16px' }}>
        <RobotOutlined style={{ marginRight: '8px' }} />
        设备详情
      </Title>

      {robotIds.length === 0 ? (
        <Card style={{ textAlign: 'center', padding: '48px' }}>
          <Text type="secondary" style={{ fontSize: '16px' }}>
            暂无在线机器人，请检查后端连接或等待机器人上线
          </Text>
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {robotIds.map((robotId, index) => (
            <Col xs={24} sm={12} lg={8} xl={6} key={robotId}>
              <RobotCard robotId={robotId} index={index} />
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
};
