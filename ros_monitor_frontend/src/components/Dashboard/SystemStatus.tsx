import React from 'react';
import { Card, Row, Col, Statistic, Badge, Space, Typography, Divider } from 'antd';
import { 
  WifiOutlined,
  ApiOutlined,
  RobotOutlined,
  CameraOutlined,
  RadarChartOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  AimOutlined
} from '@ant-design/icons';
import { useSystemStore } from '../../stores/useSystemStore';
import { useSensorStore } from '../../stores/useSensorStore';
import { StatusBadge, getStatusColor } from '../../utils/statusHelpers';

const { Title, Text } = Typography;

export const SystemStatus: React.FC = () => {
  const { connection, performance } = useSystemStore();
  const { robotData, activeRobotId } = useSensorStore();
  
  // 获取当前选中机器人的传感器数据
  const robotState = activeRobotId ? robotData[activeRobotId] : null;
  const camera = robotState?.camera ?? { left: null, right: null, status: { connected: false, lastUpdate: 0, frequency: 0, errorCount: 0 } };
  const lidar  = robotState?.lidar  ?? { latest: null, status: { connected: false, lastUpdate: 0, frequency: 0, errorCount: 0 } };
  const gnss   = robotState?.gnss   ?? { latest: null, history: [], status: { connected: false, lastUpdate: 0, frequency: 0, errorCount: 0 } };
  

  const formatFrequency = (freq: number) => 
    freq > 0 ? `${freq.toFixed(1)} Hz` : '0 Hz';

  return (
    <div style={{ width: '100%' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '32px', textAlign: 'center' }}>
        <Title level={2} style={{ color: '#1890ff', marginBottom: '12px' }}>
          <DashboardOutlined style={{ marginRight: '12px' }} />
          ROS系统监控仪表盘
        </Title>
        <Text type="secondary" style={{ fontSize: '16px' }}>
          实时监控ROS系统状态、连接性能和传感器数据
        </Text>
      </div>

      <Row gutter={[16, 16]}>
        {/* 连接状态卡片 */}
        <Col xs={24} sm={12} lg={8}>
          <Card title="连接状态" size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <WifiOutlined />
                  <span>WebSocket</span>
                </Space>
                <StatusBadge connected={connection.websocket} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <ApiOutlined />
                  <span>API</span>
                </Space>
                <StatusBadge connected={connection.api} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <RobotOutlined />
                  <span>ROS</span>
                </Space>
                <StatusBadge connected={connection.ros} />
              </div>
            </Space>
          </Card>
        </Col>

        {/* 性能指标卡片 */}
        <Col xs={24} sm={12} lg={8}>
          <Card 
            title={
              <Space>
                <ClockCircleOutlined style={{ color: '#1890ff' }} />
                <span>性能指标</span>
              </Space>
            } 
            size="small"
            style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
          >
            <Row gutter={16}>
              <Col span={12}>
                <Statistic
                  title="延迟"
                  value={connection.latency}
                  suffix="ms"
                  prefix={<ClockCircleOutlined style={{ color: '#1890ff' }} />}
                  valueStyle={{ color: connection.latency < 100 ? '#52c41a' : connection.latency < 300 ? '#faad14' : '#ff4d4f' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="错误计数"
                  value={performance.errorCount}
                  valueStyle={{ 
                    color: performance.errorCount > 0 ? '#cf1322' : '#3f8600',
                    fontSize: '24px'
                  }}
                />
              </Col>
            </Row>
          </Card>
        </Col>

        {/* 传感器状态卡片 */}
        <Col xs={24} lg={8}>
          <Card 
            title={
              <Space>
                <RadarChartOutlined style={{ color: '#1890ff' }} />
                <span>传感器状态</span>
              </Space>
            } 
            size="small"
            style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                padding: '8px 0',
                borderBottom: '1px solid #f0f0f0'
              }}>
                <Space>
                  <CameraOutlined style={{ color: getStatusColor(camera.status.connected) }} />
                  <span>相机</span>
                </Space>
                <Space>
                  <StatusBadge connected={camera.status.connected} />
                  <span style={{ fontSize: '12px', color: '#666' }}>
                    {formatFrequency(camera.status.frequency)}
                  </span>
                </Space>
              </div>
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                padding: '8px 0',
                borderBottom: '1px solid #f0f0f0'
              }}>
                <Space>
                  <RadarChartOutlined style={{ color: getStatusColor(lidar.status.connected) }} />
                  <span>激光雷达</span>
                </Space>
                <Space>
                  <StatusBadge connected={lidar.status.connected} />
                  <span style={{ fontSize: '12px', color: '#666' }}>
                    {formatFrequency(lidar.status.frequency)}
                  </span>
                </Space>
              </div>
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                padding: '8px 0'
              }}>
                <Space>
                  <AimOutlined style={{ color: getStatusColor(gnss.status.connected) }} />
                  <span>GNSS/RTK</span>
                </Space>
                <Space>
                  <StatusBadge connected={gnss.status.connected} />
                  <span style={{ fontSize: '12px', color: '#666' }}>
                    {formatFrequency(gnss.status.frequency)}
                  </span>
                </Space>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      <Divider />

      {/* 数据统计 */}
      <Row gutter={[16, 16]}>

        <Col xs={12} sm={6}>
          <Card 
            style={{ 
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              textAlign: 'center'
            }}
          >
            <Statistic
              title="运行时间"
              value={Math.floor(performance.uptime / 60)}
              suffix="分钟"
              valueStyle={{ color: '#1890ff', fontSize: '28px' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card 
            style={{ 
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              textAlign: 'center'
            }}
          >
            <Statistic
              title="数据传输率"
              value={performance.dataRate}
              suffix="KB/s"
              valueStyle={{ color: '#52c41a', fontSize: '28px' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card 
            style={{ 
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              textAlign: 'center'
            }}
          >
            <Statistic
              title="系统状态"
              value={connection.websocket && connection.api && connection.ros ? '健康' : '异常'}
              valueStyle={{ 
                color: connection.websocket && connection.api && connection.ros ? '#52c41a' : '#ff4d4f',
                fontSize: '28px'
              }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card 
            style={{ 
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              textAlign: 'center'
            }}
          >
            <Statistic
              title="在线传感器"
              value={[camera.status.connected, lidar.status.connected, gnss.status.connected].filter(Boolean).length}
              suffix="/ 3"
              valueStyle={{ color: '#1890ff', fontSize: '28px' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 系统信息 */}
      <Row style={{ marginTop: '24px' }}>
        <Col span={24}>
          <Card 
            title={
              <Space>
                <RobotOutlined style={{ color: '#1890ff' }} />
                <span>系统信息</span>
              </Space>
            }
            style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
          >
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={8}>
                <Text strong>系统状态:</Text> <Text>{connection.websocket && connection.api ? '运行中' : '待连接'}</Text>
              </Col>
              <Col xs={24} sm={8}>
                <Text strong>WebSocket:</Text> <Text>{connection.websocket ? '已连接' : '未连接'}</Text>
              </Col>
              <Col xs={24} sm={8}>
                <Text strong>ROS就绪:</Text> <Text>{connection.ros ? '是' : '否'}</Text>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

