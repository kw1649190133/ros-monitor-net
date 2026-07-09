import React, { useEffect, useRef } from 'react';
import { Card, Statistic, Row, Col, Tag, Space, Typography } from 'antd';
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  WarningOutlined,
  AimOutlined
} from '@ant-design/icons';
import { useSensorStore } from '../../stores/useSensorStore';
import type { RTKStatus } from '../../types/gnss';
import { wsService } from '../../services/websocket';

const { Text } = Typography;

const GNSSStatusPanel: React.FC = () => {
  const { robotData, activeRobotId } = useSensorStore();
  const gnss = activeRobotId ? robotData[activeRobotId]?.gnss : null;
  const latest = gnss?.latest || null;
  
  // 订阅GNSS话题
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const retries = useRef(0);
  
  useEffect(() => {
    // 等待WebSocket连接后再订阅（带重试上限和清理）
    const subscribeGNSS = () => {
      if (wsService.isConnected()) {
        wsService.subscribe(['gnss']);
        return;
      }
      retries.current += 1;
      if (retries.current < 20) {
        timerRef.current = setTimeout(subscribeGNSS, 500);
      }
    };
    
    subscribeGNSS();
    
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsService.isConnected()) {
        wsService.unsubscribe(['gnss']);
      }
    };
  }, []);
  
  if (!latest) {
    return (
      <Card title="GNSS/RTK 状态">
        <Text type="secondary">暂无GNSS数据</Text>
      </Card>
    );
  }
  
  /**
   * 获取RTK状态的显示配置
   */
  const getRTKStatusConfig = (status: RTKStatus) => {
    switch (status) {
      case 'RTK_FIXED':
        return { 
          color: 'success', 
          icon: <CheckCircleOutlined />, 
          text: 'RTK固定解',
          description: '最高精度定位'
        };
      case 'RTK_FLOAT':
        return { 
          color: 'warning', 
          icon: <WarningOutlined />, 
          text: 'RTK浮点解',
          description: '中等精度定位'
        };
      case 'GPS_3D':
        return { 
          color: 'processing', 
          icon: <AimOutlined />, 
          text: '3D定位',
          description: '普通GPS定位'
        };
      case 'GPS_2D':
        return { 
          color: 'default', 
          icon: <WarningOutlined />, 
          text: '2D定位',
          description: '平面定位'
        };
      case 'GPS_1D':
        return { 
          color: 'default', 
          icon: <WarningOutlined />, 
          text: '单点定位',
          description: '基础定位'
        };
      default:
        return { 
          color: 'error', 
          icon: <CloseCircleOutlined />, 
          text: '无定位',
          description: '信号丢失'
        };
    }
  };
  
  const statusConfig = getRTKStatusConfig(latest.rtk_status);
  
  /**
   * 根据卫星数量获取颜色
   */
  const getSatelliteColor = (numSv: number) => {
    if (numSv >= 15) return '#52c41a'; // 绿色
    if (numSv >= 10) return '#faad14'; // 橙色
    return '#ff4d4f'; // 红色
  };
  
  return (
    <Card title="GNSS/RTK 状态监控" style={{ height: '100%' }}>
      {/* RTK状态和卫星数 */}
      <Row gutter={[16, 16]}>
        <Col span={16}>
          <Card size="small" bordered={false}>
            <Space direction="vertical" size="small">
              <Space>
                {statusConfig.icon}
                <Tag color={statusConfig.color} style={{ fontSize: '14px' }}>
                  {statusConfig.text}
                </Tag>
              </Space>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                {statusConfig.description}
              </Text>
            </Space>
          </Card>
        </Col>
        <Col span={8}>
          <Statistic 
            title="卫星数量" 
            value={latest.quality.num_sv}
            suffix="颗"
            valueStyle={{ color: getSatelliteColor(latest.quality.num_sv) }}
          />
        </Col>
      </Row>
      
      {/* 精度信息 */}
      <Card size="small" title="定位精度" style={{ marginTop: 16 }}>
        <Row gutter={[16, 16]}>
          <Col span={8}>
            <Statistic 
              title="水平精度" 
              value={latest.accuracy.h_acc}
              precision={3}
              suffix="m"
              valueStyle={{ 
                color: latest.accuracy.h_acc < 0.1 ? '#52c41a' : '#faad14' 
              }}
            />
          </Col>
          <Col span={8}>
            <Statistic 
              title="垂直精度" 
              value={latest.accuracy.v_acc}
              precision={3}
              suffix="m"
              valueStyle={{ 
                color: latest.accuracy.v_acc < 0.1 ? '#52c41a' : '#faad14' 
              }}
            />
          </Col>
          <Col span={8}>
            <Statistic 
              title="PDOP" 
              value={latest.accuracy.p_dop}
              precision={2}
              valueStyle={{ 
                color: latest.accuracy.p_dop < 2 ? '#52c41a' : '#faad14' 
              }}
            />
          </Col>
        </Row>
      </Card>
      
      {/* 位置信息 */}
      <Card size="small" title="位置信息" style={{ marginTop: 16 }}>
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Statistic 
              title="纬度" 
              value={latest.position.latitude}
              precision={7}
              suffix="°"
            />
          </Col>
          <Col span={12}>
            <Statistic 
              title="经度" 
              value={latest.position.longitude}
              precision={7}
              suffix="°"
            />
          </Col>
          <Col span={12}>
            <Statistic 
              title="海拔" 
              value={latest.position.height_msl}
              precision={2}
              suffix="m"
            />
          </Col>
          <Col span={12}>
            <Statistic 
              title="椭球高" 
              value={latest.position.altitude}
              precision={2}
              suffix="m"
            />
          </Col>
        </Row>
      </Card>
      
      {/* 详细质量信息 */}
      <Card size="small" title="定位质量" style={{ marginTop: 16 }}>
        <Row gutter={[8, 8]}>
          <Col span={12}>
            <Space>
              <Text type="secondary">定位有效:</Text>
              <Tag color={latest.quality.valid_fix ? 'success' : 'error'}>
                {latest.quality.valid_fix ? '是' : '否'}
              </Tag>
            </Space>
          </Col>
          <Col span={12}>
            <Space>
              <Text type="secondary">差分解:</Text>
              <Tag color={latest.quality.diff_soln ? 'success' : 'default'}>
                {latest.quality.diff_soln ? '已应用' : '未应用'}
              </Tag>
            </Space>
          </Col>
          <Col span={12}>
            <Space>
              <Text type="secondary">定位类型:</Text>
              <Tag>{latest.quality.fix_type}D</Tag>
            </Space>
          </Col>
          <Col span={12}>
            <Space>
              <Text type="secondary">载波解:</Text>
              <Tag color={latest.quality.carr_soln === 2 ? 'success' : 'default'}>
                {latest.quality.carr_soln}
              </Tag>
            </Space>
          </Col>
        </Row>
      </Card>
      
      {/* GPS时间 */}
      <Card size="small" title="GPS时间" style={{ marginTop: 16 }}>
        <Space split="|">
          <Text>
            <Text type="secondary">周数:</Text> {latest.time.week}
          </Text>
          <Text>
            <Text type="secondary">周内秒:</Text> {latest.time.tow.toFixed(1)}s
          </Text>
          <Text>
            <Text type="secondary">帧号:</Text> {latest.sequence}
          </Text>
        </Space>
      </Card>
    </Card>
  );
};

export default GNSSStatusPanel;
