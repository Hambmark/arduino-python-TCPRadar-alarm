# gui_manager.py
# 管理 GUI 元素（按钮、滑块）及其回调函数。
import time

import matplotlib.pyplot as plt        # 主要用于创建 Axes 对象
from matplotlib.widgets import Button, Slider # 导入按钮和滑块控件
from . import config


# 注意：这个模块不直接导入 arduino_comm，而是通过初始化时传入连接对象

class GuiManager:
    """创建和管理 GUI 控件，并将它们连接到相应的动作。"""

    def __init__(self, fig, arduino_connection, data_saver_func, stop_func, close_func):
        """
        初始化 GUI 管理器。
        :param fig: Matplotlib Figure 对象，控件将添加到此 Figure 上。
        :param arduino_connection: ArduinoConnection 对象实例，用于发送指令。
        :param data_saver_func: 当“保存数据”按钮被点击时要调用的函数。
        :param stop_func: 当“停止程序”按钮被点击时要调用的函数。
        :param close_func: 当“关闭绘图”按钮被点击时要调用的函数。
        """
        self.fig = fig                          # Figure 对象
        self.arduino_comm = arduino_connection  # Arduino 通信对象
        self.save_data_callback = data_saver_func # 保存按钮的回调
        self.stop_callback = stop_func            # 停止按钮的回调
        self.close_callback = close_func          # 关闭按钮的回调

        # 用于存储控件对象的引用（如果后续需要访问）
        self.button_close = None
        self.button_save = None
        self.button_stop = None
        self.slider_min_angle = None
        self.slider_max_angle = None
        self.slider_scan_step = None
        self.slider_scan_delay = None

        self._setup_widgets() # 调用内部方法创建控件

    def _setup_widgets(self):
        """创建所有的按钮和滑块控件。"""
        # --- 按钮 ---
        # 位置参数：[左边距, 下边距, 宽度, 高度] (均以 Figure 比例表示 0-1)
        # 调整位置以确保它们在底部且不与滑块重叠
        close_ax = self.fig.add_axes([0.8, 0.15, 0.15, 0.04]) # 右下区域
        self.button_close = Button(close_ax, '关闭绘图', color=config.BUTTON_COLOR, hovercolor=config.HOVER_COLOR)
        self.button_close.on_clicked(self._on_close) # 绑定回调
        self.button_close.label.set_color(config.BUTTON_TEXT_COLOR)

        save_ax = self.fig.add_axes([0.8, 0.09, 0.15, 0.04]) # 关闭按钮下方
        self.button_save = Button(save_ax, '保存数据', color=config.BUTTON_COLOR, hovercolor=config.HOVER_COLOR)
        self.button_save.on_clicked(self._on_save)
        self.button_save.label.set_color(config.BUTTON_TEXT_COLOR)

        stop_ax = self.fig.add_axes([0.8, 0.03, 0.15, 0.04]) # 保存按钮下方
        self.button_stop = Button(stop_ax, '停止程序', color=config.BUTTON_COLOR, hovercolor=config.HOVER_COLOR)
        self.button_stop.on_clicked(self._on_stop)
        self.button_stop.label.set_color(config.BUTTON_TEXT_COLOR)

        # --- 滑块 ---
        # 滑块放在按钮左侧
        ax_min = plt.axes([0.1, 0.15, 0.6, 0.02], facecolor=config.BUTTON_COLOR) # 底部靠上
        self.slider_min_angle = Slider(ax_min, '最小角度', 0, 179, valinit=0, valstep=1, color=config.SLIDER_COLOR)
        self.slider_min_angle.on_changed(self._update_min_angle) # 绑定回调

        ax_max = plt.axes([0.1, 0.11, 0.6, 0.02], facecolor=config.BUTTON_COLOR) # 上一个滑块下方
        self.slider_max_angle = Slider(ax_max, '最大角度', 1, 180, valinit=180, valstep=1, color=config.SLIDER_COLOR)
        self.slider_max_angle.on_changed(self._update_max_angle)

        ax_step = plt.axes([0.1, 0.07, 0.6, 0.02], facecolor=config.BUTTON_COLOR)
        self.slider_scan_step = Slider(ax_step, '扫描步进', 1, 30, valinit=5, valstep=1, color=config.SLIDER_COLOR)
        self.slider_scan_step.on_changed(self._update_scan_step)

        ax_delay = plt.axes([0.1, 0.03, 0.6, 0.02], facecolor=config.BUTTON_COLOR) # 最下方滑块
        self.slider_scan_delay = Slider(ax_delay, '扫描延迟(ms)', 10, 200, valinit=50, valstep=5, color=config.SLIDER_COLOR)
        self.slider_scan_delay.on_changed(self._update_scan_delay)

    # --- 内部回调处理函数 ---
    # 这些函数会调用在初始化时传入的外部函数

    def _on_stop(self, event):
        """处理停止按钮点击事件。"""
        if self.stop_callback:
            self.stop_callback()

    def _on_close(self, event):
        """处理关闭按钮点击事件。"""
        if self.close_callback:
            self.close_callback()

    def _on_save(self, event):
        """处理保存按钮点击事件。"""
        if self.save_data_callback:
            self.save_data_callback()

    # --- 滑块值改变的处理函数 ---

    def _update_min_angle(self, val):
        """当最小角度滑块值改变时调用。"""
        # 可选：在此处添加验证逻辑，例如确保 min_angle < max_angle
        # if val >= self.slider_max_angle.val:
        #     self.slider_min_angle.set_val(self.slider_max_angle.val - 1) # 自动调整
        #     return # 阻止发送无效值
        self.arduino_comm.send_command('a', val) # 发送 'a' 指令

    def _update_max_angle(self, val):
        """当最大角度滑块值改变时调用。"""
        # 可选：添加验证逻辑
        # if val <= self.slider_min_angle.val:
        #     self.slider_max_angle.set_val(self.slider_min_angle.val + 1)
        #     return
        self.arduino_comm.send_command('A', val) # 发送 'A' 指令

    def _update_scan_step(self, val):
        """当扫描步进滑块值改变时调用。"""
        self.arduino_comm.send_command('S', val) # 发送 'S' 指令

    def _update_scan_delay(self, val):
        """当扫描延迟滑块值改变时调用。"""
        self.arduino_comm.send_command('D', val) # 发送 'D' 指令

    # --- 公共方法 (可选) ---

    def get_slider_values(self):
        """返回所有滑块当前值的字典。"""
        if not all([self.slider_min_angle, self.slider_max_angle, self.slider_scan_step, self.slider_scan_delay]):
             return {} # 如果控件未完全初始化，返回空字典
        return {
            'min_angle': self.slider_min_angle.val,
            'max_angle': self.slider_max_angle.val,
            'scan_step': self.slider_scan_step.val,
            'scan_delay': self.slider_scan_delay.val
        }

    def set_initial_arduino_params(self):
         """将当前滑块的初始值发送给 Arduino。"""
         print("正在发送初始参数给 Arduino...")
         # 依次发送每个参数，中间加少量延迟确保 Arduino 能处理
         self._update_min_angle(self.slider_min_angle.val)
         time.sleep(0.1)
         self._update_max_angle(self.slider_max_angle.val)
         time.sleep(0.1)
         self._update_scan_step(self.slider_scan_step.val)
         time.sleep(0.1)
         self._update_scan_delay(self.slider_scan_delay.val)