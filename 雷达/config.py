# config.py
# 雷达应用程序的配置常量

# --- 显示与绘图 ---
R_MAX = 100.0       # 最大显示距离 (厘米) - 应与 Arduino MAX_DISTANCE_CM 协调
UPDATE_INTERVAL_S = 0.05 # 目标绘图更新间隔 (秒)
PLOT_BG_COLOR = '#262626'       # 绘图背景色
PLOT_GRID_COLOR = '#808080'     # 绘图网格线颜色
PLOT_TICK_COLOR = '#d0d0d0'     # 绘图刻度标签颜色
SCAN_LINE_COLOR = '#00ff00'     # 扫描线颜色
WINDOW_BG_COLOR = '#1a1a1a'       # 窗口背景色
WINDOW_TITLE = 'Arduino 雷达扫描仪 (模块化版)' # 窗口标题
POINT_SIZE = 35                  # 探测点大小
# 按距离变化的探测点颜色映射表 (从近到远)
POINT_CMAP = ["#00a0ff", "#00e0e0", "#ffff00"]
OBJECT_MARKER_COLOR = 'magenta'  # 对象标记填充色
OBJECT_MARKER_EDGE_COLOR = 'white'# 对象标记边缘色
OBJECT_MARKER_SIZE = 10          # 对象标记大小
OBJECT_MARKER_ALPHA = 0.7        # 对象标记透明度

# --- 数据处理 ---
FILTER_WINDOW = 3       # 移动平均滤波窗口大小
INITIAL_ALPHA = 1.0     # 新探测点的初始透明度 (用于拖尾效果)
ALPHA_DECAY_RATE = 0.08 # 每个更新周期透明度的衰减量 (越大衰减越快)
OBJECT_MIN_POINTS = 3   # 识别为对象所需得最少连续点数
OBJECT_MAX_GAP = 2      # 对象内部允许的最大连续无效点数量（以角度步长计）

# --- Arduino 通信 ---
BAUD_RATE = 115200                # 串口波特率
SERIAL_TIMEOUT_S = 1              # 串口读取超时时间 (秒)
START_SIGNAL = "Radar Start"      # Arduino 启动完成时发送的信号
# Arduino 发送的表示无效/超范围距离的标记值
# 必须与 Arduino 代码中的 INVALID_DISTANCE_MARKER 匹配
ARDUINO_INVALID_DIST_MARKER = R_MAX + 1.0

# --- GUI 控制 ---
BUTTON_COLOR = '#cccccc'          # 按钮默认颜色
HOVER_COLOR = '#e0e0e0'           # 按钮悬停颜色
SLIDER_COLOR = '#007acc'          # 滑块颜色
BUTTON_TEXT_COLOR = 'k'           # 按钮文字颜色

# --- 字体设置 ---
# 尝试使用常见中文字体，如果需要可添加更多备选项
FONT_PREFERENCES = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']