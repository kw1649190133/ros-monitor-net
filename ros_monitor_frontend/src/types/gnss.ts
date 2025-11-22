/**
 * GNSS/RTK数据类型定义
 */

/**
 * GPS时间信息
 */
export interface GNSSTime {
  week: number;      // GPS周数
  tow: number;       // 周内秒(Time of Week)
}

/**
 * GNSS位置信息
 */
export interface GNSSPosition {
  latitude: number;   // 纬度(度)
  longitude: number;  // 经度(度)
  altitude: number;   // 椭球高(米)
  height_msl: number; // 海拔高度(米, Mean Sea Level)
}

/**
 * GNSS精度信息
 */
export interface GNSSAccuracy {
  h_acc: number;  // 水平精度(米)
  v_acc: number;  // 垂直精度(米)
  p_dop: number;  // 位置精度因子(Position Dilution of Precision)
}

/**
 * GNSS速度信息
 */
export interface GNSSVelocity {
  vel_n: number;   // 北向速度(m/s)
  vel_e: number;   // 东向速度(m/s)
  vel_d: number;   // 下向速度(m/s)
  vel_acc: number; // 速度精度(m/s)
}

/**
 * GNSS定位质量信息
 */
export interface GNSSQuality {
  fix_type: number;      // 定位类型: 0=无定位, 1=单点, 2=2D, 3=3D
  valid_fix: boolean;    // 定位有效性
  diff_soln: boolean;    // 是否应用差分改正
  carr_soln: number;     // 载波解状态: 0=无, 1=浮点解, 2=固定解
  num_sv: number;        // 使用的卫星数量
}

/**
 * RTK定位状态类型
 */
export type RTKStatus = 
  | 'RTK_FIXED'  // ✅ RTK固定解(最高精度)
  | 'RTK_FLOAT'  // ⚠️ RTK浮点解(中等精度)
  | 'GPS_3D'     // 📡 3D定位(普通GPS)
  | 'GPS_2D'     // 📡 2D定位
  | 'GPS_1D'     // 单点定位
  | 'NO_FIX';    // ❌ 无定位

/**
 * GNSS完整数据结构
 */
export interface GNSSData {
  rtk_status: RTKStatus;       // RTK状态
  quality: GNSSQuality;        // 定位质量
  position: GNSSPosition;      // 位置信息
  accuracy: GNSSAccuracy;      // 精度信息
  velocity: GNSSVelocity;      // 速度信息
  time: GNSSTime;              // GPS时间
  timestamp: number;           // Unix时间戳
  sequence: number;            // 帧序号
}
