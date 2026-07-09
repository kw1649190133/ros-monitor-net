// WebSocket 消息类型定义 — Discriminated Union

import type { CameraData, LidarData, PathData, OdometryData, RegisteredCloudData } from './sensors';
import type { GNSSData } from './gnss';

// ---- 服务端 → 客户端消息 ----

export interface WSConnectedMessage {
  type: 'connected';
  client_id: string;
  message: string;
}

export interface WSSubscribedMessage {
  type: 'subscribed' | 'subscription_confirmed';
  topics: string[];
  message?: string;
}

export interface WSUnsubscribedMessage {
  type: 'unsubscribed';
  topics: string[];
  message?: string;
}

export interface WSCameraMessage {
  type: 'camera';
  robot_id?: string;
  camera_id: string;
  timestamp: number;
  data: CameraData;
}

export interface WSLidarMessage {
  type: 'lidar';
  robot_id?: string;
  timestamp: number;
  data: LidarData;
}

export interface WSIMUMessage {
  type: 'imu';
  robot_id?: string;
  timestamp: number;
  data: {
    timestamp: number;
    orientation: { x: number; y: number; z: number; w: number };
    angular_velocity: { x: number; y: number; z: number };
    linear_acceleration: { x: number; y: number; z: number };
  };
}

export interface WSGNSSMessage {
  type: 'gnss';
  robot_id?: string;
  timestamp: number;
  data: GNSSData;
}

export interface WSPathMessage {
  type: 'slam_path';
  robot_id?: string;
  timestamp: number;
  data: PathData;
}

export interface WSOdometryMessage {
  type: 'slam_odometry';
  robot_id?: string;
  timestamp: number;
  data: OdometryData;
}

export interface WSCloudMessage {
  type: 'slam_cloud';
  robot_id?: string;
  timestamp: number;
  data: RegisteredCloudData;
}

export interface WSRobotListMessage {
  type: 'robot_list_updated';
  robots: string[];
  count: number;
  traffic: Record<string, { total_kb: number; rate_kbps: number }>;
  timestamp: number;
}

export interface WSSystemStatusMessage {
  type: 'system_status';
  ros_ready: boolean;
  websocket_status: string;
  api_status: boolean;
  ros_info: Record<string, unknown> | null;
  timestamp: number;
}

export interface WSAckMessage {
  type: 'ack';
  message?: string;
}

export interface WSErrorMessage {
  type: 'error';
  message: string;
  code?: number;
}

export interface WSRobotCommandSentMessage {
  type: 'robot_command_sent';
  robot_id: string;
  command: Record<string, unknown>;
  message?: string;
}

/** 统一的入库消息类型 — Discriminated Union，禁止 any */
export type InboundMessage =
  | WSConnectedMessage
  | WSSubscribedMessage
  | WSUnsubscribedMessage
  | WSCameraMessage
  | WSLidarMessage
  | WSIMUMessage
  | WSGNSSMessage
  | WSPathMessage
  | WSOdometryMessage
  | WSCloudMessage
  | WSRobotListMessage
  | WSSystemStatusMessage
  | WSAckMessage
  | WSErrorMessage
  | WSRobotCommandSentMessage;

// ---- 客户端 → 服务端消息 ----

export interface OutboundSubscribe {
  type: 'subscribe';
  topics?: string[];
  data?: { topics: string[] };
  timestamp?: string;
}

export interface OutboundUnsubscribe {
  type: 'unsubscribe';
  topics?: string[];
  data?: { topics: string[] };
  timestamp?: string;
}

export interface OutboundPing {
  type: 'ping';
  timestamp?: string;
}

export interface OutboundSystemStatus {
  type: 'request_system_status';
  timestamp?: string;
}

export interface OutboundRobotCommand {
  type: 'robot_command';
  robot_id: string;
  command: Record<string, unknown>;
  timestamp?: string;
}

export interface OutboundSelectRobot {
  type: 'select_robot';
  robot_id: string;
}

export type OutboundMessage =
  | OutboundSubscribe
  | OutboundUnsubscribe
  | OutboundPing
  | OutboundSystemStatus
  | OutboundRobotCommand
  | OutboundSelectRobot;
