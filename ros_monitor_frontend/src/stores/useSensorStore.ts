import { create } from 'zustand';
import type { CameraData, LidarData, SensorStatus, PathData, OdometryData, RegisteredCloudData } from '../types/sensors';
import type { GNSSData } from '../types/gnss';


interface SensorStore {
  // 相机数据
  camera: {
    left: CameraData | null;
    right: CameraData | null;
    status: SensorStatus;
  };

  // 激光雷达数据
  lidar: {
    latest: LidarData | null;
    status: SensorStatus;
  };

  // GNSS数据
  gnss: {
    latest: GNSSData | null;
    history: GNSSData[];
    status: SensorStatus;
  };

  // SLAM数据
  slam: {
    path: PathData | null;
    odometry: OdometryData | null;
    registeredCloud: RegisteredCloudData | null;
    pathHistory: PathData[];  // 保存历史轨迹用于绘制
    cloudHistory: RegisteredCloudData[];  // 累积点云历史用于地图显示
    decayTime: number;  // 点云衰减时间(秒)
    status: SensorStatus;
  };

  // Actions
  updateCameraData: (camera: 'left' | 'right', data: CameraData) => void;
  updateLidarData: (data: LidarData) => void;
  updateGNSSData: (data: GNSSData) => void;
  updatePathData: (data: PathData) => void;
  updateOdometryData: (data: OdometryData) => void;
  updateRegisteredCloudData: (data: RegisteredCloudData) => void;
  setDecayTime: (decayTime: number) => void;
  updateSensorStatus: (sensor: 'camera' | 'lidar' | 'gnss' | 'slam', status: Partial<SensorStatus>) => void;
  clearGNSSData: () => void;
  clearSLAMData: () => void;
  clearAllData: () => void;
}

const initialSensorStatus: SensorStatus = {
  connected: false,
  lastUpdate: 0,
  frequency: 0,
  errorCount: 0,
};

export const useSensorStore = create<SensorStore>((set) => ({
  camera: {
    left: null,
    right: null,
    status: { ...initialSensorStatus },
  },
  
  lidar: {
    latest: null,
    status: { ...initialSensorStatus },
  },
  
  gnss: {
    latest: null,
    history: [],
    status: { ...initialSensorStatus },
  },

  slam: {
    path: null,
    odometry: null,
    registeredCloud: null,
    pathHistory: [],
    cloudHistory: [],
    decayTime: 180, // 默认180秒
    status: { ...initialSensorStatus },
  },

  updateCameraData: (camera: 'left' | 'right', data: CameraData) => set((state) => ({
    camera: {
      ...state.camera,
      [camera]: data,
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.camera.status.frequency,
        errorCount: state.camera.status.errorCount,
      },
    },
  })),
  
  updateLidarData: (data: LidarData) => set((state) => ({
    lidar: {
      latest: data,
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.lidar.status.frequency,
        errorCount: state.lidar.status.errorCount,
      },
    },
  })),
  
  updateGNSSData: (data: GNSSData) => set((state) => ({
    gnss: {
      latest: data,
      history: [...state.gnss.history.slice(-99), data], // 保留最近100条
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.gnss.status.frequency,
        errorCount: state.gnss.status.errorCount,
      },
    },
  })),

  updatePathData: (data: PathData) => set((state) => ({
    slam: {
      ...state.slam,
      path: data,
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.slam.status.frequency,
        errorCount: state.slam.status.errorCount,
      },
    },
  })),

  updateOdometryData: (data: OdometryData) => set((state) => ({
    slam: {
      ...state.slam,
      odometry: data,
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.slam.status.frequency,
        errorCount: state.slam.status.errorCount,
      },
    },
  })),

  updateRegisteredCloudData: (data: RegisteredCloudData) => set((state) => {
    const now = Date.now() / 1000;
    const decayTime = state.slam.decayTime;

    // 过滤掉过期的点云,添加新点云
    const filteredHistory = state.slam.cloudHistory.filter(
      cloud => (now - cloud.timestamp) < decayTime
    );

    return {
      slam: {
        ...state.slam,
        registeredCloud: data,
        cloudHistory: [...filteredHistory, data],
        status: {
          connected: true,
          lastUpdate: Date.now(),
          frequency: state.slam.status.frequency,
          errorCount: state.slam.status.errorCount,
        },
      },
    };
  }),

  setDecayTime: (decayTime: number) => set((state) => ({
    slam: {
      ...state.slam,
      decayTime: decayTime,
    },
  })),

  updateSensorStatus: (sensor: 'camera' | 'lidar' | 'gnss' | 'slam', status: Partial<SensorStatus>) => set((state) => {
    if (sensor === 'camera') {
      return {
        camera: {
          ...state.camera,
          status: {
            ...state.camera.status,
            ...status,
          },
        },
      };
    } else if (sensor === 'lidar') {
      return {
        lidar: {
          ...state.lidar,
          status: {
            ...state.lidar.status,
            ...status,
          },
        },
      };
    } else if (sensor === 'gnss') {
      return {
        gnss: {
          ...state.gnss,
          status: {
            ...state.gnss.status,
            ...status,
          },
        },
      };
    } else if (sensor === 'slam') {
      return {
        slam: {
          ...state.slam,
          status: {
            ...state.slam.status,
            ...status,
          },
        },
      };
    }
    return state;
  }),

  clearGNSSData: () => set(() => ({
    gnss: {
      latest: null,
      history: [],
      status: { ...initialSensorStatus },
    },
  })),

  clearSLAMData: () => set((state) => ({
    slam: {
      path: null,
      odometry: null,
      registeredCloud: null,
      pathHistory: [],
      cloudHistory: [],
      decayTime: state.slam.decayTime, // 保留decayTime设置
      status: { ...initialSensorStatus },
    },
  })),

  clearAllData: () => set((state) => ({
    camera: {
      left: null,
      right: null,
      status: { ...initialSensorStatus },
    },
    lidar: {
      latest: null,
      status: { ...initialSensorStatus },
    },
    gnss: {
      latest: null,
      history: [],
      status: { ...initialSensorStatus },
    },
    slam: {
      path: null,
      odometry: null,
      registeredCloud: null,
      pathHistory: [],
      cloudHistory: [],
      decayTime: state.slam.decayTime, // 保留decayTime设置
      status: { ...initialSensorStatus },
    },
  })),
}));

