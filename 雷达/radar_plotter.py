# radar_plotter.py
# 处理 Matplotlib 雷达图的创建和更新。

import matplotlib.pyplot as plt       # 导入 Matplotlib 绘图库
import matplotlib.colors as mcolors   # 用于颜色映射
import numpy as np                    # 用于数值操作
from . import config


class RadarPlotter:
    """管理 Matplotlib 雷达图的可视化。"""

    def __init__(self, fig, r_max=config.R_MAX):
        """初始化绘图器。"""
        self.fig = fig              # Matplotlib Figure 对象
        self.r_max = r_max          # 最大半径（距离）
        self.ax = None              # 极坐标轴对象 (Axes)
        self.pols = None            # 用于拖尾效果的散点图对象 (Scatter)
        self.line1 = None           # 扫描线对象 (Line2D)
        self.object_markers = None  # 用于对象标记的绘图对象 (Line2D, 'o' marker)
        self.axbackground = None    # 用于 Blitting 加速绘图的背景缓存

        self._setup_plot()        # 初始化绘图元素
        self._setup_blitting()    # 设置 Blitting

    def _setup_plot(self):
        """初始化极坐标图的坐标轴和静态元素。"""
        # 添加一个极坐标子图
        self.ax = self.fig.add_subplot(111, polar=True, facecolor=config.PLOT_BG_COLOR)
        # 设置半径（Y轴）范围
        self.ax.set_ylim([0.0, self.r_max])
        # 设置角度（X轴）范围为 0 到 180 度 (0 到 pi 弧度)
        self.ax.set_xlim([0.0, np.pi])

        # 设置图表样式
        self.ax.tick_params(axis='both', colors=config.PLOT_TICK_COLOR) # 刻度颜色
        self.ax.grid(color=config.PLOT_GRID_COLOR, alpha=0.4, linestyle='--') # 网格线
        self.ax.set_rticks(np.linspace(0.0, self.r_max, 6)) # 设置半径刻度线位置
        self.ax.set_rlabel_position(22.5) # 设置半径刻度标签的位置（角度）

        # 设置角度刻度线和标签
        angles_deg_labels = np.linspace(0.0, 180.0, 13) # 在 0-180 度间生成 13 个刻度
        angle_labels_text = [f'{int(deg)}°' for deg in angles_deg_labels] # 创建角度标签文本
        self.ax.set_thetagrids(angles_deg_labels, labels=angle_labels_text) # 应用角度刻度

        # 创建绘图元素（Artist），初始时数据为空
        # 颜色映射表
        cmap = mcolors.LinearSegmentedColormap.from_list("radar_cmap", config.POINT_CMAP)
        # 颜色标准化器
        norm = plt.Normalize(vmin=0, vmax=self.r_max)
        # 拖尾效果散点图
        self.pols = self.ax.scatter([], [], s=config.POINT_SIZE, c=[], cmap=cmap, norm=norm, alpha=None, edgecolors='face')
        # 扫描线
        self.line1, = self.ax.plot([], color=config.SCAN_LINE_COLOR, linewidth=3.0, alpha=0.9)
        # 对象标记（使用 plot 实现带标记的散点效果）
        self.object_markers, = self.ax.plot([], [], 'o',  # 'o' 表示圆形标记
                                            markersize=config.OBJECT_MARKER_SIZE,
                                            markerfacecolor=config.OBJECT_MARKER_COLOR,
                                            markeredgecolor=config.OBJECT_MARKER_EDGE_COLOR,
                                            alpha=config.OBJECT_MARKER_ALPHA,
                                            linestyle='None',  # 不显示连接线
                                            label='识别对象') # 图例标签
        # self.ax.legend() # 可选：如果需要显示图例则取消注释

    def _setup_blitting(self):
        """设置 Blitting 所需的资源（缓存背景）。"""
        # 必须先绘制一次画布，确保所有静态元素（坐标轴、网格等）都已渲染
        self.fig.canvas.draw()
        # 拷贝当前坐标轴区域的像素作为背景缓存
        # 必须在所有静态元素绘制完成后执行
        self.axbackground = self.fig.canvas.copy_from_bbox(self.ax.bbox)

    def update_plot(self, fade_data, object_data, scan_angle_deg):
        """使用新数据更新绘图，采用 Blitting 技术加速。"""
        # 解包传入的数据
        fade_thetas, fade_radii, fade_alphas, fade_colors = fade_data
        obj_thetas, obj_radii = object_data

        # --- 更新拖尾效果的点 ---
        if len(fade_thetas) > 0: # 仅在有数据时更新
            # vstack 用于将角度和半径合并为 (N, 2) 的坐标数组
            offsets = np.vstack((fade_thetas, fade_radii)).T
            self.pols.set_offsets(offsets)    # 更新点的位置
            self.pols.set_array(fade_colors)  # 更新点的颜色数据（基于距离）
            self.pols.set_alpha(fade_alphas)  # 更新点的透明度
        else:
            # 如果没有活动点，则清空散点图数据
            self.pols.set_offsets(np.empty((0, 2)))
            self.pols.set_alpha(None)

        # --- 更新对象标记 ---
        # set_data 用于更新 Line2D 对象的数据（这里用于标记点）
        self.object_markers.set_data(obj_thetas, obj_radii)

        # --- 更新扫描线 ---
        scan_angle_rad = scan_angle_deg * (np.pi / 180.0) # 角度转弧度
        # 设置扫描线的起点和终点（角度相同，半径从 0 到 r_max）
        self.line1.set_data([scan_angle_rad, scan_angle_rad], [0, self.r_max])

        # --- 执行 Blitting 绘图更新 ---
        try:
            # 1. 恢复缓存的背景
            self.fig.canvas.restore_region(self.axbackground)
            # 2. 绘制需要更新的动态元素（Artist）
            self.ax.draw_artist(self.pols)
            self.ax.draw_artist(self.line1)
            self.ax.draw_artist(self.object_markers)
            # 3. 将更新后的坐标轴区域“印”到画布上
            self.fig.canvas.blit(self.ax.bbox)
            # 4. 刷新画布事件，确保更新显示在屏幕上
            self.fig.canvas.flush_events()
        except Exception as e:
            # 如果 Blitting 失败（有时会发生，尤其在窗口交互时）
            # 则回退到较慢但更稳定的完整重绘方式
            # print(f"Blitting 失败 ({e})，尝试使用 draw_idle() 回退。") # 调试信息
            try:
                # draw_idle 请求画布在下一个 GUI 事件循环空闲时重绘
                self.fig.canvas.draw_idle()
                self.fig.canvas.flush_events() # 确保请求被处理
            except Exception as draw_e:
                 # 如果回退也失败，打印错误
                 print(f"回退绘图方法 draw_idle() 也失败: {draw_e}")