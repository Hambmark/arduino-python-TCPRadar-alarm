# data_processor.py
# 包含处理原始雷达数据的功能。

from collections import deque  # 用于实现固定长度队列（滤波历史）

import numpy as np  # 用于数值计算和 NaN 处理

from . import config


class DataProcessor:
    """处理雷达数据的过滤和对象检测。"""

    def __init__(self, num_angles=181, filter_window=config.FILTER_WINDOW):
        """初始化数据处理器。"""
        self.num_angles = num_angles          # 雷达扫描的角度数量 (0-180度，共181个点)
        self.filter_window = filter_window    # 滤波窗口大小
        # 初始化数据结构
        # 滤波历史：一个列表，每个元素是对应角度的 deque (双端队列)
        self.filter_history = [deque(maxlen=self.filter_window) for _ in range(num_angles)]
        # 存储滤波后的最新距离值，初始全部为 NaN
        self.filtered_dists = np.full((num_angles,), np.nan)
        # 活动点列表：存储用于拖尾效果的点信息
        self.active_points = [] # 每个元素是字典: {'theta': 弧度, 'radius': 距离, 'alpha': 透明度}
        # 识别出的对象列表：存储识别出的对象信息
        self.identified_objects = [] # 每个元素是字典: {'center_theta': 弧度, 'center_radius': 距离}

    def reset(self):
        """重置所有存储的数据（例如，当雷达重新启动时）。"""
        self.filtered_dists.fill(np.nan) # 重置滤波距离
        self.active_points.clear()       # 清空活动点
        self.identified_objects.clear()  # 清空已识别对象
        for history_deque in self.filter_history: # 清空所有角度的滤波历史
            history_deque.clear()
        print("数据处理器已重置。")

    def process_new_data(self, angle_deg, dist_raw):
        """处理单个新的数据点：进行滤波并更新活动点列表。"""
        # 验证角度有效性
        if not (0 <= angle_deg <= 180):
            # print(f"警告：接收到无效角度 {angle_deg}。")
            return None # 如果角度无效，返回 None

        # --- 处理原始距离 ---
        # 检查是否为 Arduino 发送的无效距离标记值或小于等于 0
        if dist_raw >= config.ARDUINO_INVALID_DIST_MARKER or dist_raw <= 0:
            dist_processed = np.nan # 无效距离处理为 NaN
        else:
            dist_processed = dist_raw # 有效距离直接使用

        # --- 应用移动平均滤波 ---
        # 将当前处理后的距离（可能是 NaN）加入对应角度的历史队列
        self.filter_history[angle_deg].append(dist_processed)
        # 从历史队列中筛选出有效的（非 NaN）距离值
        valid_history = [d for d in self.filter_history[angle_deg] if not np.isnan(d)]
        # 如果历史中有有效值，计算其平均值作为滤波结果
        if valid_history:
            filtered_dist = np.mean(valid_history)
            self.filtered_dists[angle_deg] = filtered_dist # 更新存储的滤波距离
        else:
            # 如果历史中全是 NaN，则滤波结果也是 NaN
            filtered_dist = np.nan
            self.filtered_dists[angle_deg] = np.nan

        # --- 更新活动点列表 (用于拖尾效果) ---
        angle_rad = angle_deg * (np.pi / 180.0) # 将角度转换为弧度
        found = False
        # 遍历当前活动点列表
        for point in self.active_points:
            # 检查是否存在对应角度的点（允许非常小的角度误差）
            if abs(point['theta'] - angle_rad) < 0.01:
                # 如果找到了对应角度的点
                if not np.isnan(filtered_dist): # 并且当前滤波后的距离有效
                    point['radius'] = filtered_dist      # 更新点的距离
                    point['alpha'] = config.INITIAL_ALPHA # 重置点的透明度 (使其完全不透明)
                # else: # 如果当前距离无效，则不更新，让该点自然衰减
                found = True # 标记已找到
                break        # 跳出循环

        # 如果列表中没有找到该角度的点，并且当前滤波距离有效
        if not found and not np.isnan(filtered_dist):
            # 添加一个新的活动点
            self.active_points.append({
                'theta': angle_rad,          # 角度 (弧度)
                'radius': filtered_dist,     # 距离 (滤波后)
                'alpha': config.INITIAL_ALPHA # 初始透明度
            })

        return filtered_dist # 返回当前角度的滤波后距离

    def update_fade_effect(self):
        """更新活动点的透明度，并移除已完全褪色的点。"""
        next_active_points = [] # 用于存储下一轮仍然活动的点
        for point in self.active_points:
            point['alpha'] -= config.ALPHA_DECAY_RATE # 减少透明度
            # 如果透明度仍然大于一个很小的值（避免浮点数精度问题），则保留该点
            if point['alpha'] > 0.01:
                next_active_points.append(point)
        self.active_points = next_active_points # 更新活动点列表

    def detect_objects(self, angles_rad):
        """根据最新地滤波距离数据检测对象。"""
        # 调用内部的识别逻辑函数
        self.identified_objects = self._find_objects_internal(
            angles_rad,                   # 角度数组 (弧度)
            self.filtered_dists,          # 当前滤波后的距离数组
            config.OBJECT_MIN_POINTS,     # 配置中定义的最小点数
            config.OBJECT_MAX_GAP         # 配置中定义的最大允许间隙
        )
        return self.identified_objects # 返回识别出的对象列表

    def _find_objects_internal(self, angles_rad, distances, min_points, max_gap):
        """查找连续有效距离段的内部逻辑。"""
        objects = []             # 存储找到的对象
        in_segment = False       # 当前是否在有效段内
        segment_start_idx = -1   # 当前有效段的起始索引
        gap_count = 0            # 当前连续无效点的计数

        # 在距离数组末尾添加一个 NaN，以确保最后一个有效段能被正确处理
        padded_distances = np.append(distances, np.nan)

        # 遍历（包含填充NaN的）距离数组
        for i in range(len(padded_distances)):
            # 检查当前点是否有效（非 NaN）
            is_valid = not np.isnan(padded_distances[i])

            if is_valid:
                gap_count = 0 # 如果有效，重置间隙计数
                if not in_segment: # 如果之前不在段内，说明新段开始
                    in_segment = True
                    segment_start_idx = i
            else: # 当前点无效
                if in_segment: # 如果之前在段内
                    gap_count += 1 # 增加间隙计数
                    # 如果间隙超过允许值，或者到达数组末尾，则结束当前段
                    if gap_count > max_gap or i == len(padded_distances) - 1:
                        # 计算段的结束索引（不包括导致结束的无效点）
                        segment_end_idx = i - gap_count
                        # 检查段的长度是否满足最小点数要求
                        if (segment_end_idx - segment_start_idx + 1) >= min_points:
                            # 如果满足，认为是一个对象
                            # 计算对象中心（简单取段的中间索引）
                            center_idx = segment_start_idx + (segment_end_idx - segment_start_idx) // 2
                            # 再次确认中心点的距离值是有效的
                            if 0 <= center_idx <= segment_end_idx and not np.isnan(distances[center_idx]):
                                # 添加对象信息到列表
                                objects.append({
                                    'center_theta': angles_rad[center_idx], # 中心角度
                                    'center_radius': distances[center_idx], # 中心距离
                                    'start_theta': angles_rad[segment_start_idx], # 起始角度
                                    'end_theta': angles_rad[segment_end_idx]   # 结束角度
                                })
                        # 重置段追踪状态
                        in_segment = False
                        segment_start_idx = -1
                        gap_count = 0
        return objects # 返回找到的对象列表

    def get_plot_data_fade(self):
        """返回用于绘制拖尾效果散点图的数据。"""
        if not self.active_points: # 如果没有活动点
            return [], [], [], []  # 返回空列表
        # 从 active_points 列表中提取角度、半径、透明度和颜色数据
        thetas = np.array([p['theta'] for p in self.active_points])
        radii = np.array([p['radius'] for p in self.active_points])
        alphas = np.array([p['alpha'] for p in self.active_points])
        colors = radii # 使用半径（距离）作为颜色映射的依据
        return thetas, radii, alphas, colors

    def get_plot_data_objects(self):
        """返回用于绘制对象标记的数据。"""
        if not self.identified_objects: # 如果没有识别出对象
            return [], []             # 返回空列表
        # 从 identified_objects 列表中提取中心角度和半径
        thetas = np.array([obj['center_theta'] for obj in self.identified_objects])
        radii = np.array([obj['center_radius'] for obj in self.identified_objects])
        return thetas, radii

    def get_filtered_data_for_saving(self):
         """返回适合保存到文件的当前过滤后的数据。"""
         data_to_save = []
         # 遍历所有角度的滤波后距离
         for angle_deg, dist in enumerate(self.filtered_dists):
             # 只保存有效的距离值
             if not np.isnan(dist):
                  # 将距离保留两位小数后添加到列表
                  data_to_save.append([angle_deg, round(dist, 2)])
         return data_to_save