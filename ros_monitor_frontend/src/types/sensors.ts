// 传感器数据类型定义

export interface CameraData {
  camera_id: string;
  timestamp: number;
  sequence: number;
  encoding: string;
  width: number;
  height: number;
  data: string; // Base64编码的图像数据
  compressed: boolean;
}

export interface LidarData {
  timestamp: number;
  frame_id: string;
  point_count: number;
  points: number[]; // 点云数据数组
}

export interface SensorStatus {
  connected: boolean;
  lastUpdate: number;
  frequency: number;
  errorCount: number;
}

// SLAM相关数据类型
export interface Pose {
  position: {
    x: number;
    y: number;
    z: number;
  };
  orientation: {
    x: number;
    y: number;
    z: number;
    w: number;
  };
}

export interface PathData {
  topic: string;
  timestamp: number;
  frame_id: string;
  sequence: number;
  total_poses: number;
  sampled_poses: number;
  poses: Pose[];
}

export interface OdometryData {
  topic: string;
  timestamp: number;
  frame_id: string;
  child_frame_id: string;
  sequence: number;
  pose: Pose;
  twist: {
    linear: { x: number; y: number; z: number };
    angular: { x: number; y: number; z: number };
  };
}

export interface RegisteredCloudData {
  topic: string;
  timestamp: number;
  frame_id: string;
  sequence: number;
  total_points: number;
  sampled_points: number;
  points: number[][]; // [[x,y,z], [x,y,z], ...]
  colors?: number[][]; // [[r,g,b], [r,g,b], ...] 0-255
  has_rgb?: boolean;
  fields: string[];
}

export interface SLAMData {
  path: PathData | null;
  odometry: OdometryData | null;
  registeredCloud: RegisteredCloudData | null;
  status: SensorStatus;
}

