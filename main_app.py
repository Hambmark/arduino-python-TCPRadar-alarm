# main_app.py
# Arduino 雷达1 GUI 的主应用程序脚本。

import matplotlib.pyplot as plt
import numpy as np
import time
import csv
from datetime import datetime
import traceback

# 导入我们自己创建的模块
# 导入我们自己创建的模块 (使用包路径)
from 雷达 import config  # 导入 config 模块本身

from 雷达.arduino_comm import ArduinoConnection # 从 雷达 包的 arduino_comm 模块导入类
from 雷达.data_processor import DataProcessor   # 从 雷达 包的 data_processor 模块导入类
from 雷达.radar_plotter import RadarPlotter     # 从 雷达 包的 radar_plotter 模块导入类
from 雷达.gui_manager import GuiManager         # 从 雷达 包的 gui_manager 模块导入类

# --- 字体设置函数 ---
def setup_fonts():
    """尝试设置字体首选项，如果找不到则发出警告。"""
    for font_name in config.FONT_PREFERENCES:
        try:
            plt.rcParams['font.sans-serif'] = [font_name]
            plt.rcParams['axes.unicode_minus'] = False
            print(f"使用字体: {font_name}")
            return True
        except Exception:
            continue
    print("警告：未能找到任何偏好的字体。中文字符可能无法正确显示。")
    return False

class RadarApplication:
    """协调雷达应用程序各个组件和主循环。"""

    def __init__(self):
        """初始化应用程序。"""
        setup_fonts()

        self.arduino = ArduinoConnection()
        self.processor = DataProcessor()
        self.fig = plt.figure(facecolor=config.WINDOW_BG_COLOR)
        self.fig.set_size_inches(10, 1)
        plt.subplots_adjust(bottom=0.25, top=0.95)

        self.plotter = RadarPlotter(self.fig)
        self.gui = GuiManager(
            self.fig,
            self.arduino,
            data_saver_func=self.save_data,
            stop_func=self.request_stop,        # 传递请求停止的函数引用
            close_func=self.request_close       # *** 传递请求关闭的函数引用 ***
        )

        self.is_running = True          # *** 修改：初始设为 True ***
        self.stop_requested = False     # 是否请求停止处理
        self.close_requested = False    # 是否请求关闭窗口
        self.last_valid_angle_deg = 0
        self.theta_rad_range = np.arange(0, 181, 1) * (np.pi / 180.0)

    def request_stop(self):
        """仅标记停止处理数据和绘图更新。"""
        print("已请求停止处理。")
        self.stop_requested = True
        # *** 不再直接设置 is_running = False ***

    def request_close(self):
        """标记停止处理并请求关闭应用程序和窗口。"""
        print("已请求关闭。")
        self.close_requested = True
        self.stop_requested = True # 关闭同时也意味着停止处理
        self.is_running = False    # *** 设置 is_running 为 False 以便退出循环 ***

    def save_data(self):
        """将当前过滤后的雷达数据保存到 CSV 文件。"""
        # ... (保存数据逻辑保持不变) ...
        data_to_save = self.processor.get_filtered_data_for_saving()
        if not data_to_save:
            print("没有有效的雷达数据可供保存。")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"radar_data_{timestamp}.csv"
        print(f"正在保存数据到 {filename}...")
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Angle (degrees)', 'Distance (cm)'])
                writer.writerows(data_to_save)
            print("数据保存成功。")
        except Exception as e:
            print(f"保存数据时发生错误: {e}")

    def run(self):
        """启动应用程序的主事件循环。"""
        if not self.arduino.connect():
            print("退出：无法连接到 Arduino。")
            return

        print("应用程序启动中...")
        plt.ion()
        self.fig.show()
        self.fig.canvas.flush_events()

        last_update_time = time.time()

        # *** 修改主循环逻辑 ***
        while self.is_running:
            current_time = time.time()

            # --- 仅在未请求停止时执行数据处理和绘图 ---
            if not self.stop_requested:
                # --- 读取和处理 Arduino 数据 ---
                try:
                    status, data_lines = self.arduino.read_data()

                    if status == "DISCONNECTED":
                        print("Arduino 已断开连接。正在停止应用程序。")
                        self.request_close() # 连接断开，直接请求关闭
                        continue # 跳过本次循环的剩余部分
                    elif status == "STARTED":
                        print("雷达确认启动。正在重置数据并发送初始参数。")
                        self.processor.reset()
                        self.gui.set_initial_arduino_params()
                    elif status == "ERROR":
                        print("发生串口读取错误。")

                    if data_lines:
                        last_valid_data_line = None
                        for line in reversed(data_lines):
                            if ',' in line:
                                last_valid_data_line = line
                                break

                        if last_valid_data_line:
                            try:
                                vals = [float(ii) for ii in last_valid_data_line.split(',')]
                                if len(vals) == 2:
                                    angle_deg, dist_raw = vals
                                    angle_deg = int(round(angle_deg))
                                    self.last_valid_angle_deg = angle_deg
                                    self.processor.process_new_data(angle_deg, dist_raw)
                            except ValueError: pass
                            except IndexError: pass

                except Exception as e:
                    print("串口读取/处理时发生错误:")
                    traceback.print_exc()

                # --- 定期更新绘图 ---
                if current_time - last_update_time >= config.UPDATE_INTERVAL_S:
                    last_update_time = current_time

                    self.processor.update_fade_effect()
                    self.processor.detect_objects(self.theta_rad_range)

                    fade_plot_data = self.processor.get_plot_data_fade()
                    object_plot_data = self.processor.get_plot_data_objects()

                    self.plotter.update_plot(fade_plot_data, object_plot_data, self.last_valid_angle_deg)

            # --- else: 如果 stop_requested 为 True，则跳过上面的所有处理 ---

            # --- 保持 GUI 响应并检查窗口是否关闭 ---
            # 无论是否停止处理，都需要调用 pause 来处理 GUI 事件
            try:
                 plt.pause(0.01) # 短暂暂停，处理事件，避免 CPU 满载
            except Exception:
                # 处理窗口被用户手动关闭的情况
                if not plt.fignum_exists(self.fig.number):
                     print("绘图窗口已被手动关闭。正在停止程序。")
                     self.is_running = False # 确保循环退出
                     self.close_requested = True # 标记为需要关闭（虽然已经关了）
                     break # 直接退出循环

            # *** 在循环末尾检查 is_running 状态，如果 request_close 设置了它为 False，则退出 ***
            # (上面的 break 也可以处理，这里是双重保险)
            # if not self.is_running:
            #      break

        # --- 程序结束前的清理工作 ---
        print("正在关闭应用程序...")
        self.arduino.disconnect() # 断开 Arduino 连接

        # *** 修改关闭逻辑：如果窗口还存在并且请求了关闭，则尝试关闭 ***
        # (如果窗口已被手动关闭，plt.close 可能无效果或报错，所以加检查)
        if self.close_requested and plt.fignum_exists(self.fig.number):
             try:
                 plt.close(self.fig.number) # 尝试关闭指定的 Figure
                 print("绘图窗口已关闭。")
             except Exception as e:
                 print(f"关闭绘图窗口时发生错误: {e}")
        elif not self.close_requested:
            # 如果只是停止处理，但未请求关闭
            print("应用程序已停止处理。窗口保持打开状态。")
            # 在这种情况下，可能不需要 plt.ioff() 和 plt.show() 了，
            # 因为程序即将退出，窗口会自动关闭或变为无响应。
            # 可以选择留空，让操作系统处理窗口。

        print("应用程序已结束。")


# --- 程序入口点 ---
if __name__ == "__main__":
    app = RadarApplication()
    try:
        app.run()
    except Exception as e:
        print("\n--- 发生未处理的异常 ---")
        traceback.print_exc()
        print("--- 应用程序因错误而终止 ---")
        if app.arduino and app.arduino.is_connected():
            app.arduino.disconnect()
        try:
            # 尝试关闭所有可能存在的 matplotlib 窗口
            plt.close('all')
        except Exception:
            pass