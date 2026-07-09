import { create } from 'zustand';
import type { CameraData, LidarData, SensorStatus, PathData, OdometryData, RegisteredCloudData } from '../types/sensors';
import type { GNSSData } from '../types/gnss';


// ---- 单机器人传感器状态 ----

export interface RobotSensorState {
  camera: {
    left: CameraData | null;
    right: CameraData | null;
    status: SensorStatus;
  };
  lidar: {
    latest: LidarData | null;
    status: SensorStatus;
  };
  gnss: {
    latest: GNSSData | null;
    history: GNSSData[];
    status: SensorStatus;
  };
  slam: {
    path: PathData | null;
    odometry: OdometryData | null;
    registeredCloud: RegisteredCloudData | null;
    pathHistory: PathData[];
    cloudHistory: RegisteredCloudData[];
    decayTime: number;
    status: SensorStatus;
  };
}

const initialSensorStatus: SensorStatus = {
  connected: false,
  lastUpdate: 0,
  frequency: 0,
  errorCount: 0,
};

function createRobotState(): RobotSensorState {
  return {
    camera: { left: null, right: null, status: { ...initialSensorStatus } },
    lidar: { latest: null, status: { ...initialSensorStatus } },
    gnss: { latest: null, history: [], status: { ...initialSensorStatus } },
    slam: {
      path: null, odometry: null, registeredCloud: null,
      pathHistory: [], cloudHistory: [],
      decayTime: 180, status: { ...initialSensorStatus },
    },
  };
}

function ensureRobot(state: SensorStore, robotId: string): RobotSensorState {
  if (!state.robotData[robotId]) {
    state.robotData[robotId] = createRobotState();
  }
  return state.robotData[robotId];
}


// ---- Store ----

interface SensorStore {
  // 多机器人数据
  robotData: Record<string, RobotSensorState>;
  robotIds: string[];
  activeRobotId: string | null;

  // 机器人管理
  setRobotList: (ids: string[]) => void;
  setActiveRobot: (robotId: string | null) => void;
  removeRobot: (robotId: string) => void;

  // 数据更新（所有函数接受 robotId）
  updateCameraData: (robotId: string, camera: 'left' | 'right', data: CameraData) => void;
  updateLidarData: (robotId: string, data: LidarData) => void;
  updateGNSSData: (robotId: string, data: GNSSData) => void;
  updatePathData: (robotId: string, data: PathData) => void;
  updateOdometryData: (robotId: string, data: OdometryData) => void;
  updateRegisteredCloudData: (robotId: string, data: RegisteredCloudData) => void;
  setDecayTime: (robotId: string, decayTime: number) => void;
  updateSensorStatus: (robotId: string, sensor: 'camera' | 'lidar' | 'gnss' | 'slam', status: Partial<SensorStatus>) => void;

  // 清理
  clearGNSSData: (robotId: string) => void;
  clearSLAMData: (robotId: string) => void;
  clearAllData: () => void;
}

export const useSensorStore = create<SensorStore>((set, get) => ({
  robotData: {},
  robotIds: [],
  activeRobotId: null,

  // ---- 机器人管理 ----

  setRobotList: (ids: string[]) => set((state) => {
    // 保留已有机器人数据，只更新列表
    const existingIds = Object.keys(state.robotData);
    const newIds = ids.filter(id => !existingIds.includes(id));
    
    // 为新机器人创建初始状态
    for (const id of newIds) {
      if (!state.robotData[id]) {
        state.robotData[id] = createRobotState();
      }
    }
    
    return {
      robotIds: ids,
      // 如果当前选中的机器人不在线，自动选第一个
      activeRobotId: state.activeRobotId && ids.includes(state.activeRobotId)
        ? state.activeRobotId
        : ids[0] || null,
    };
  }),

  setActiveRobot: (robotId: string | null) => set({ activeRobotId: robotId }),
  
  removeRobot: (robotId: string) => set((state) => {
    const newData = { ...state.robotData };
    delete newData[robotId];
    const newIds = state.robotIds.filter(id => id !== robotId);
    return {
      robotData: newData,
      robotIds: newIds,
      activeRobotId: state.activeRobotId === robotId ? (newIds[0] || null) : state.activeRobotId,
    };
  }),

  // ---- 数据更新 ----

  updateCameraData: (robotId: string, camera: 'left' | 'right', data: CameraData) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.camera[camera] = data;
      robot.camera.status = { ...robot.camera.status, connected: true, lastUpdate: Date.now() };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  updateLidarData: (robotId: string, data: LidarData) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.lidar.latest = data;
      robot.lidar.status = { ...robot.lidar.status, connected: true, lastUpdate: Date.now() };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  updateGNSSData: (robotId: string, data: GNSSData) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.gnss.latest = data;
      robot.gnss.history = [...robot.gnss.history.slice(-99), data];
      robot.gnss.status = { ...robot.gnss.status, connected: true, lastUpdate: Date.now() };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  updatePathData: (robotId: string, data: PathData) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.slam.path = data;
      robot.slam.pathHistory = [...robot.slam.pathHistory.slice(-49), data];
      robot.slam.status = { ...robot.slam.status, connected: true, lastUpdate: Date.now() };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  updateOdometryData: (robotId: string, data: OdometryData) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.slam.odometry = data;
      robot.slam.status = { ...robot.slam.status, connected: true, lastUpdate: Date.now() };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  updateRegisteredCloudData: (robotId: string, data: RegisteredCloudData) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      const now = Date.now() / 1000;
      const decayTime = robot.slam.decayTime;
      const filteredHistory = robot.slam.cloudHistory.filter(
        cloud => (now - ((cloud as any)._received_at ?? cloud.timestamp)) < decayTime
      );
      robot.slam.registeredCloud = data;
      robot.slam.cloudHistory = [...filteredHistory, data];
      robot.slam.status = { ...robot.slam.status, connected: true, lastUpdate: Date.now() };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  setDecayTime: (robotId: string, decayTime: number) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.slam.decayTime = decayTime;
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  updateSensorStatus: (robotId: string, sensor: 'camera' | 'lidar' | 'gnss' | 'slam', status: Partial<SensorStatus>) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot[sensor].status = { ...robot[sensor].status, ...status };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  // ---- 清理 ----

  clearGNSSData: (robotId: string) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.gnss = { latest: null, history: [], status: { ...initialSensorStatus } };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  clearSLAMData: (robotId: string) =>
    set((state) => {
      const robot = ensureRobot(state, robotId);
      robot.slam = {
        path: null, odometry: null, registeredCloud: null,
        pathHistory: [], cloudHistory: [],
        decayTime: robot.slam.decayTime,
        status: { ...initialSensorStatus },
      };
      return { robotData: { ...state.robotData, [robotId]: robot } };
    }),

  clearAllData: () => set({ robotData: {}, robotIds: [], activeRobotId: null }),
}));
