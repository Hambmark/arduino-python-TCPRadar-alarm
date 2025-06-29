# -*- coding: utf-8 -*-
# 导入所需库
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Canvas
import serial
import serial.tools.list_ports
import sqlite3
import datetime
import time
import threading
import traceback
import queue
from PIL import Image, ImageTk
import os
import math
import socket
import json
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
# from matplotlib.widgets import Slider # Using tk.Scale

# --- 常量定义 ---
DB_NAME = "sensor_data.db"
ARDUINO_BAUDRATE = 115200
SERIAL_TIMEOUT = 1.0
CMD_RADAR_OFF = "RADAR_OFF\n"
CMD_ALARM_PREFIX = "ALARM "
RESPONSE_POLL_INTERVAL = 100
THREAD_JOIN_TIMEOUT = 1.0
DATA_VIEW_INTERVAL_MS = 1000
DATA_VIEW_REQUEST_DELAY_MS = 500
CMD_LIGHT_ON = "command=arduino1\n"
CMD_LIGHT_OFF = "command=arduino2\n"
CMD_GET_TEMP = "command=arduino3\n"
CMD_GET_HUMI = "command=arduino4\n"
CMD_RADAR_ON = "RADAR_ON\n"
CMD_RADAR_OFF = "RADAR_OFF\n"
CMD_RADAR_PREFIX_MAX_ANGLE = 'A'
CMD_RADAR_PREFIX_MIN_ANGLE = 'a'
CMD_RADAR_PREFIX_STEP = 'S'
CMD_RADAR_PREFIX_DELAY = 'D'
BG_IMG_FILENAME = "background3.png"
LIGHT_OFF_IMG_FILENAME = "background1.png"
LIGHT_ON_IMG_FILENAME = "background2.png"
BTN_ON_IMG_FILENAME = "btn_on.png"
BTN_OFF_IMG_FILENAME = "btn_off.png"
BTN_TEMP_IMG_FILENAME = "btn_temp.png"
BTN_HUM_IMG_FILENAME = "btn_hum.png"
IMAGE_STATUS_SIZE = (150, 150)
BUTTON_IMAGE_SIZE = (100, 40)
PLOT_WINDOW_WIDTH = 750
PLOT_WINDOW_HEIGHT = 650
PLOT_CANVAS_WIDTH = 700
PLOT_CANVAS_HEIGHT = 400
PLOT_MARGIN = 50
PLOT_POINTS = 50
PLOT_TEMP_COLOR = "red"
PLOT_HUMI_COLOR = "blue"
PLOT_AXIS_COLOR = "black"
PLOT_GRID_COLOR = "#E0E0E0"
ARDUINO_KEYWORDS = ['CH340', 'Arduino', 'Serial', 'ttyACM', 'ttyUSB']
USE_SOCKET = False
SERVER_IP = ""#你本地设备的公网IP
SERVER_PORT = 8888
SOCKET_TIMEOUT = 5
SOCKET_RECONNECT_INTERVAL = 5
DEVICE_ID = "MyDHT_Client_01"
RADAR_R_MAX = 100.0
RADAR_UPDATE_INTERVAL_S = 0.05
RADAR_INVALID_MARKER = RADAR_R_MAX + 1.0
GAUGE_MAX_TEMP = 50.0
GAUGE_MAX_HUMI = 100.0
USE_SOCKET = True # <<< 设为 True 来测试
DEVICE_ID = "MyDHT_Client_01" # <<< 确保与服务器端协调一致

# --- 仪表盘类 ---
class RectGauge:
    """在Canvas上绘制和更新矩形仪表盘"""
    def __init__(self, canvas, x, y, width, height, min_val=0, max_val=100, label="数值", color="green", outline_color="black", text_color="black", num_ticks=6):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.min_val = min_val
        self.max_val = max_val
        self.label = label
        self.color = color
        self.outline_color = outline_color
        self.text_color = text_color
        self.num_ticks = max(2, num_ticks)
        self.value_rect_id = None
        self.text_id = None
        self._draw_base()

    def _value_to_y(self, value):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            value = self.min_val
        clamped_value = max(self.min_val, min(self.max_val, value))
        range_val = self.max_val - self.min_val
        proportion = (clamped_value - self.min_val) / range_val if range_val != 0 else 0
        return self.y + self.height - (self.height * proportion)

    def _draw_base(self):
        self.canvas.create_rectangle(self.x, self.y, self.x + self.width, self.y + self.height,
                                     outline=self.outline_color, fill="white", width=1)
        tick_x_start = self.x - 5
        tick_x_end = self.x
        label_x = self.x - 8
        original_range_val = self.max_val - self.min_val
        safe_range_val = original_range_val if original_range_val != 0 else 1.0
        num_intervals = self.num_ticks - 1 if self.num_ticks > 1 else 1
        for i in range(self.num_ticks):
            val = self.min_val + (safe_range_val * i / num_intervals)
            tick_y = self._value_to_y(val)
            self.canvas.create_line(tick_x_start, tick_y, tick_x_end, tick_y, fill=self.outline_color)
            self.canvas.create_text(label_x, tick_y, text=f"{val:.0f}", anchor=tk.E,
                                    fill=self.text_color, font=("Segoe UI", 7))
        self.canvas.create_text(self.x + self.width / 2, self.y + self.height + 10,
                                text=self.label, anchor=tk.N,
                                fill=self.text_color, font=("Segoe UI", 8, "bold"))
        self.text_id = self.canvas.create_text(self.x + self.width / 2, self.y - 10,
                                               text="--", anchor=tk.S,
                                               fill=self.text_color, font=("Segoe UI", 8))

    def update_value(self, value):
        if self.value_rect_id:
             try:
                 self.canvas.delete(self.value_rect_id)
             except tk.TclError:
                 pass # Ignore error if canvas/item gone
             self.value_rect_id = None # Ensure ID is cleared
        if self.text_id:
            is_invalid = value is None or (isinstance(value, float) and math.isnan(value))
            display_text = "N/A" if is_invalid else f"{value:.1f}"
            try:
                 self.canvas.itemconfig(self.text_id, text=display_text)
            except tk.TclError:
                 pass
        if value is not None and isinstance(value, (int, float)) and not math.isnan(value):
            fill_y_start = self._value_to_y(value)
            fill_y_start = max(self.y, min(self.y + self.height, fill_y_start))
            fill_y_end = self.y + self.height
            if fill_y_start < fill_y_end:
                 try:
                      self.value_rect_id = self.canvas.create_rectangle(self.x, fill_y_start, self.x + self.width, fill_y_end, outline="", fill=self.color)
                 except tk.TclError:
                      self.value_rect_id = None

class RadialGauge:
    """在Canvas上绘制和更新半圆形仪表盘"""
    def __init__(self, canvas, cx, cy, radius, min_val=0, max_val=100, label="数值", pointer_color="red", arc_color="black", text_color="black", num_ticks=11):
        self.canvas = canvas
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.min_val = min_val
        self.max_val = max_val
        self.label = label
        self.pointer_color = pointer_color
        self.arc_color = arc_color
        self.text_color = text_color
        self.num_ticks = max(2, num_ticks)
        self.pointer_id = None
        self.text_id = None
        self._draw_base()

    def _value_to_angle_deg(self, value):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            value = self.min_val
        clamped_value = max(self.min_val, min(self.max_val, value))
        range_val = self.max_val - self.min_val
        proportion = (clamped_value - self.min_val) / range_val if range_val != 0 else 0
        return 180 - (proportion * 180)

    def _draw_base(self):
        """绘制仪表盘的静态背景、刻度和标签"""
        x0 = self.cx - self.radius
        y0 = self.cy - self.radius
        x1 = self.cx + self.radius
        y1 = self.cy + self.radius
        self.canvas.create_arc(x0, y0, x1, y1, start=0, extent=180, style=tk.ARC, outline=self.arc_color, width=2)

        original_range_val = self.max_val - self.min_val
        safe_range_val = original_range_val if original_range_val != 0 else 1.0
        tick_len_inner = self.radius - 8
        tick_len_outer = self.radius
        label_radius = self.radius + 12
        num_intervals = self.num_ticks - 1 if self.num_ticks > 1 else 1

        for i in range(self.num_ticks):
            val = self.min_val + (safe_range_val * i / num_intervals)
            angle_deg = self._value_to_angle_deg(val)
            angle_rad = math.radians(angle_deg)
            # Calculate tick points
            x1_t = self.cx + tick_len_inner * math.cos(angle_rad)
            y1_t = self.cy - tick_len_inner * math.sin(angle_rad) # Y inverted
            x2_t = self.cx + tick_len_outer * math.cos(angle_rad)
            y2_t = self.cy - tick_len_outer * math.sin(angle_rad)
            self.canvas.create_line(x1_t, y1_t, x2_t, y2_t, fill=self.arc_color, width=1)
            # Calculate label points
            lx = self.cx + label_radius * math.cos(angle_rad)
            ly = self.cy - label_radius * math.sin(angle_rad) # Y inverted
            self.canvas.create_text(lx, ly, text=f"{val:.0f}", fill=self.text_color, font=("Segoe UI", 7))

        self.canvas.create_text(self.cx, self.cy + 10, text=self.label, anchor=tk.N, fill=self.text_color, font=("Segoe UI", 8, "bold"))
        self.text_id = self.canvas.create_text(self.cx, self.cy - 15, text="--", anchor=tk.CENTER, fill=self.text_color, font=("Segoe UI", 10, "bold"))


    def update_value(self, value):
        """更新指针位置和值文本"""
        if self.pointer_id:
            try:
                self.canvas.delete(self.pointer_id)
            except tk.TclError:
                pass
            self.pointer_id = None
        if self.text_id:
            is_invalid = value is None or (isinstance(value, float) and math.isnan(value))
            display_text = "N/A" if is_invalid else f"{value:.1f}"
            try:
                self.canvas.itemconfig(self.text_id, text=display_text)
            except tk.TclError:
                pass
        if value is not None and isinstance(value, (int, float)) and not math.isnan(value):
            angle_deg = self._value_to_angle_deg(value)
            angle_rad = math.radians(angle_deg)
            pointer_len = self.radius - 15
            px = self.cx + pointer_len * math.cos(angle_rad)
            py = self.cy - pointer_len * math.sin(angle_rad) # Y inverted
            try:
                self.pointer_id = self.canvas.create_line(self.cx, self.cy, px, py, width=2, fill=self.pointer_color, arrow=tk.LAST)
            except tk.TclError:
                self.pointer_id = None

# --- 雷达扫描窗口类 ---
class RadarWindow:
    # ... (与上次提供的代码一致, 内部已拆分好语句) ...
    def __init__(self, parent_window, send_cmd_callback, radar_off_callback):
        self.parent = parent_window
        self.send_command = send_cmd_callback # Function to send commands like A180
        self.on_close_callback = radar_off_callback # Function to call when window closes

        self.top_level = tk.Toplevel(parent_window)
        self.top_level.title("雷达扫描视图")
        self.top_level.geometry("1920x1080")
        self.top_level.transient(parent_window)
        self.top_level.protocol("WM_DELETE_WINDOW", self._handle_close)

        self.fig = Figure(figsize=(5.5, 5.5), dpi=100, facecolor='#1a1a1a')
        self.ax = self.fig.add_subplot(111, polar=True, facecolor='#262626')
        self._setup_radar_plot()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.top_level)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.canvas.draw()

        control_frame = tk.Frame(self.top_level, pady=10)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10)
        self._create_radar_controls(control_frame)

        self.angles_deg_range = np.arange(0, 181, 1)
        self.theta_rad_range = self.angles_deg_range * (np.pi / 180.0)
        self.latest_dists = np.full((len(self.angles_deg_range),), np.nan)
        self.last_scan_angle_deg = 0
        self.is_plotting_active = True

    def _setup_radar_plot(self):
        self.ax.set_ylim([0.0, RADAR_R_MAX])
        self.ax.set_xlim([0.0, np.pi])
        self.ax.tick_params(axis='both', colors='#d0d0d0')
        self.ax.grid(color='#808080', alpha=0.4, linestyle='--')
        self.ax.set_rticks(np.linspace(0.0, RADAR_R_MAX, 5))
        self.ax.set_rlabel_position(22.5)
        angles_deg_labels = np.linspace(0.0, 180.0, 7)
        angle_labels_text = [f'{int(deg)}°' for deg in angles_deg_labels]
        self.ax.set_thetagrids(angles_deg_labels, labels=angle_labels_text)
        self.pols = self.ax.scatter([], [], s=15, c='cyan', alpha=0.75)
        self.line1, = self.ax.plot([], color='lime', linewidth=2.0)

    def _create_radar_controls(self, parent_frame):
        slider_frame = tk.Frame(parent_frame)
        slider_frame.pack(pady=5)
        def create_slider(label, from_, to, init, step, command_prefix):
             label_widget = tk.Label(slider_frame, text=label, width=10)
             label_widget.pack(side=tk.LEFT, padx=5)
             slider = tk.Scale(slider_frame, from_=from_, to=to, resolution=step,
                               orient=tk.HORIZONTAL, length=350, showvalue=True,
                               command=lambda val, p=command_prefix: self._send_radar_param(p, val))
             slider.set(init)
             slider.pack(side=tk.LEFT, padx=5)
        create_slider("最小角度:", 0, 179, 0, 1, CMD_RADAR_PREFIX_MIN_ANGLE)
        create_slider("最大角度:", 1, 180, 180, 1, CMD_RADAR_PREFIX_MAX_ANGLE)
        create_slider("扫描步进:", 1, 20, 5, 1, CMD_RADAR_PREFIX_STEP)
        create_slider("扫描延迟(ms):", 10, 200, 50, 5, CMD_RADAR_PREFIX_DELAY)

    def _send_radar_param(self, prefix, value):
         try:
             int_value = int(float(value))
             command_str = f"{prefix}{int_value}\n"
             self.send_command(command_str)
         except ValueError:
             print(f"无效的滑块值: {value}")

    def update_radar_data(self, angle_deg, distance):
        if not self.is_plotting_active: return
        try:
            angle_deg = int(round(angle_deg))
            self.last_scan_angle_deg = angle_deg
            if 0 <= angle_deg <= 180:
                if distance >= RADAR_INVALID_MARKER or distance <= 0:
                    self.latest_dists[angle_deg] = np.nan
                else:
                    self.latest_dists[angle_deg] = min(distance, RADAR_R_MAX)
            # Schedule redraw instead of direct call to avoid GUI freezing
            self.canvas.get_tk_widget().after(10, self._redraw_radar_plot) # Schedule redraw
        except Exception as e:
            print(f"Error updating radar data: {e}")

    def _redraw_radar_plot(self):
        if not self.is_plotting_active or not self.canvas or not hasattr(self.top_level, 'winfo_exists') or not self.top_level.winfo_exists():
            return
        try:
            valid_indices = ~np.isnan(self.latest_dists)
            valid_theta = self.theta_rad_range[valid_indices]
            valid_dists = self.latest_dists[valid_indices]
            offsets = np.vstack((valid_theta, valid_dists)).T if len(valid_theta) > 0 else np.empty((0, 2))
            self.pols.set_offsets(offsets)
            scan_angle_rad = self.last_scan_angle_deg * (np.pi / 180.0)
            self.line1.set_data([scan_angle_rad, scan_angle_rad], [0, RADAR_R_MAX])
            self.canvas.draw_idle()
        except Exception as e:
            print(f"Error redrawing radar canvas: {e}")

    def _handle_close(self):
        print("Radar window closing...");
        self.is_plotting_active = False
        self.on_close_callback() # Notify main app
        # Check if top_level exists before destroying
        if hasattr(self, 'top_level') and self.top_level:
            try:
                 self.top_level.destroy()
            except tk.TclError:
                 pass # Ignore if already destroyed
        self.top_level = None # Clear reference


    def lift_window(self):
         if self.top_level and self.top_level.winfo_exists():
              self.top_level.lift(); self.top_level.focus_force()

# dht_and_radar_monitor.py

# ... (之前的导入语句) ...
# ... (RectGauge, RadialGauge, RadarWindow 类的定义) ...

# --- 数据视图窗口类 ---
class DataViewer:
    """管理显示仪表盘和历史曲线的 Toplevel 窗口"""
    # (这个类是从之前的模块化版本中提取并适配单文件环境)
    def __init__(self, parent_window, db_connection, close_callback):
        self.parent = parent_window
        # 直接使用全局变量 DB_NAME，或者考虑传入 db_connection 对象
        self.db_connection = db_connection # 使用传入的连接
        self.on_close_callback = close_callback

        self.top_level = None
        self.gauge_canvas = None
        self.history_canvas = None
        # Gauge widget references
        self.温度矩形仪表 = None # 使用中文名以匹配主应用中的引用
        self.温度圆形仪表 = None
        self.湿度矩形仪表 = None
        self.湿度圆形仪表 = None
        # History plotter instance (假设 HistoryPlotter 类也已定义)
        # 如果 HistoryPlotter 类也没有，需要一并添加
        # For simplicity here, let's assume the plotting logic is inside _绘制历史曲线图 for now
        # self.history_plotter = None # Maybe remove direct plotter instance if logic is internal

        # 背景图片需要从主应用获取或重新加载
        # 假设主应用加载了 self.绘图背景图片
        if hasattr(parent_window, '应用实例') and hasattr(parent_window.应用实例, '绘图背景图片'):
             self.绘图背景图片 = parent_window.应用实例.绘图背景图片
        else:
             self.绘图背景图片 = None # 或者尝试加载默认背景


        self._create_window()

    def _create_window(self):
        """Creates the Toplevel window and its contents."""
        if self.top_level and self.top_level.winfo_exists():
            self.top_level.lift()
            self.top_level.focus_force()
            return

        self.top_level = tk.Toplevel(self.parent)
        self.top_level.title("数据视图 (历史曲线与实时仪表)") # 中文标题
        # 使用常量
        self.top_level.geometry(f"{PLOT_WINDOW_WIDTH}x{PLOT_WINDOW_HEIGHT}")
        self.top_level.resizable(False, False)
        self.top_level.transient(self.parent)
        self.top_level.protocol("WM_DELETE_WINDOW", self.on_close_callback) # Call the main app's closer

        # Set background image if available
        if self.绘图背景图片:
             bg_label = tk.Label(self.top_level, image=self.绘图背景图片, bd=0)
             bg_label.place(x=0, y=0, relwidth=1, relheight=1)
             bg_label.lower()
        else:
             self.top_level.config(bg="#EAEAEA") # Fallback background color

        # --- Layout Frames ---
        仪表框架 = tk.Frame(self.top_level, bg="#EEEEEE", pady=5)
        仪表框架.pack(side=tk.TOP, pady=(15, 5), padx=10, fill=tk.X)
        绘图框架 = tk.Frame(self.top_level)
        绘图框架.pack(side=tk.BOTTOM, pady=(5, 15), padx=10, fill=tk.BOTH, expand=True)

        # --- Gauge Canvas & Widgets ---
        仪表画布高度 = 180
        self.实时仪表画布 = Canvas(仪表框架, width=PLOT_WINDOW_WIDTH - 40, height=仪表画布高度,
                                   bg="#F5F5F5", highlightthickness=0)
        self.实时仪表画布.pack()
        self._create_gauges() # Create the actual gauges

        # --- History Plot Canvas ---
        self.历史曲线画布 = Canvas(绘图框架, width=PLOT_CANVAS_WIDTH, height=PLOT_CANVAS_HEIGHT,
                                     bg="white", highlightthickness=1, highlightbackground="grey")
        self.历史曲线画布.pack()
        # Note: We need the _绘制历史曲线图 method here or a HistoryPlotter class

        # --- Initial Plot ---
        self.redraw_history_plot() # Draw history data on creation

    def _create_gauges(self):
        """Creates the gauge widgets on the gauge canvas."""
        # Layout parameters
        rect_w, rect_h = 30, 120
        rad_r = 55
        pad_x, pad_y = 40, 25
        # Positions
        temp_rect_x = pad_x
        temp_rad_cx = temp_rect_x + rect_w + pad_x + rad_r
        temp_cy = pad_y + rad_r + 5
        humi_rect_x = temp_rad_cx + rad_r + pad_x * 2
        humi_rad_cx = humi_rect_x + rect_w + pad_x + rad_r

        # Instantiate gauges (use RectGauge and RadialGauge classes defined above)
        # 使用常量配置最大值
        self.温度矩形仪表 = RectGauge(self.实时仪表画布, temp_rect_x, pad_y, rect_w, rect_h,
                                     min_val=0, max_val=GAUGE_MAX_TEMP, label="温度(°C)", color=PLOT_TEMP_COLOR, num_ticks=6)
        self.温度圆形仪表 = RadialGauge(self.实时仪表画布, temp_rad_cx, temp_cy, rad_r,
                                     min_val=0, max_val=GAUGE_MAX_TEMP, label="温度(°C)", pointer_color=PLOT_TEMP_COLOR, num_ticks=6)
        self.湿度矩形仪表 = RectGauge(self.实时仪表画布, humi_rect_x, pad_y, rect_w, rect_h,
                                     min_val=0, max_val=GAUGE_MAX_HUMI, label="湿度(%)", color=PLOT_HUMI_COLOR, num_ticks=6)
        self.湿度圆形仪表 = RadialGauge(self.实时仪表画布, humi_rad_cx, temp_cy, rad_r, # Use same CY
                                     min_val=0, max_val=GAUGE_MAX_HUMI, label="湿度(%)", pointer_color=PLOT_HUMI_COLOR, num_ticks=11)

    def update_gauges(self, temp=None, humi=None):
        """Updates the gauge values if the window exists."""
        if not self.is_active(): return

        # Pass values to individual gauges (they handle None/NaN internally)
        if self.温度矩形仪表: self.温度矩形仪表.update_value(temp)
        if self.温度圆形仪表: self.温度圆形仪表.update_value(temp)
        if self.湿度矩形仪表: self.湿度矩形仪表.update_value(humi)
        if self.湿度圆形仪表: self.湿度圆形仪表.update_value(humi)

    def _fetch_history_data(self):
        """Fetches recent data from the database."""
        # (与主应用中的 _获取历史数据 类似，但使用 self.db_connection)
        温度列表, 湿度列表 = [], []
        if not self.db_connection:
            print("ERROR: DataViewer has no DB connection.")
            messagebox.showerror("Database Error", "Database connection missing in Data Viewer.", parent=self.top_level)
            return None, None
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("SELECT temp FROM temperature ORDER BY id DESC LIMIT ?", (PLOT_POINTS,))
            温度列表 = [r[0] for r in cursor.fetchall() if r[0] is not None]; 温度列表.reverse()
            cursor.execute("SELECT humi FROM humidity ORDER BY id DESC LIMIT ?", (PLOT_POINTS,))
            湿度列表 = [r[0] for r in cursor.fetchall() if r[0] is not None]; 湿度列表.reverse()
            # Pad with 0.0 as per original main app logic
            温度列表 = ([0.0] * (PLOT_POINTS - len(温度列表)) + 温度列表)
            湿度列表 = ([0.0] * (PLOT_POINTS - len(湿度列表)) + 湿度列表)
            return 温度列表, 湿度列表
        except sqlite3.Error as e:
            print(f"ERROR: Failed to read history data in DataViewer: {e}")
            messagebox.showerror("Database Error", f"Failed to read history data: {e}", parent=self.top_level)
            return None, None
        except Exception as e:
            print(f"ERROR: Unexpected error fetching history in DataViewer: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred fetching history: {e}", parent=self.top_level)
            return None, None

    def redraw_history_plot(self):
        """Fetches data and redraws the history plot."""
        if not (self.is_active() and self.历史曲线画布): return

        温度列表, 湿度列表 = self._fetch_history_data()
        if 温度列表 is not None and 湿度列表 is not None:
            # Call the plotting logic (assuming _绘制历史曲线图 is defined here or accessible)
            self._绘制历史曲线图(self.历史曲线画布, 温度列表, 湿度列表) # Use local method
        else:
            # If fetching failed, display error on the plot canvas
            self.历史曲线画布.delete("all")
            self.历史曲线画布.create_text(PLOT_CANVAS_WIDTH / 2, PLOT_CANVAS_HEIGHT / 2,
                                        text="无法加载历史数据", fill="red", font=("Segoe UI", 12))

    # --- Need the plotting logic here ---
    def _绘制历史曲线图(self, 画布, 温度列表, 湿度列表):
        """在给定的 Canvas 上绘制历史温湿度曲线图 (已修正格式)"""
        # 1. 清空画布
        画布.delete("all")

        # 2. 计算绘图区域尺寸和坐标
        绘图宽度 = PLOT_CANVAS_WIDTH - 2 * PLOT_MARGIN
        绘图高度 = PLOT_CANVAS_HEIGHT - 2 * PLOT_MARGIN
        X起始 = PLOT_MARGIN
        Y起始 = PLOT_MARGIN  # 画布顶部 Y 坐标
        X结束 = PLOT_MARGIN + 绘图宽度
        Y结束 = PLOT_MARGIN + 绘图高度  # 画布底部 Y 坐标

        # 3. 绘制坐标轴线
        画布.create_line(X起始, Y结束, X结束, Y结束, fill=PLOT_AXIS_COLOR, width=1)  # X 轴
        画布.create_line(X起始, Y起始, X起始, Y结束, fill=PLOT_AXIS_COLOR, width=1)  # Y 轴

        # 4. 计算 Y 轴范围
        # 过滤掉填充值 (0.0) 来确定实际数据范围
        绘图数据 = [v for v in 温度列表 + 湿度列表 if isinstance(v, (int, float)) and v != 0.0]
        if not 绘图数据:
            # 如果没有有效数据，设置默认范围
            最小值 = 0.0
            最大值 = 10.0
        else:
            最小值 = min(绘图数据)
            最大值 = max(绘图数据)

        # 确保有最小范围并增加边界
        if 最大值 <= 最小值:
            最大值 = 最小值 + 1.0
        值范围 = 最大值 - 最小值
        Y轴最小值 = 最小值 - 值范围 * 0.1
        Y轴最大值 = 最大值 + 值范围 * 0.1
        Y轴范围 = Y轴最大值 - Y轴最小值
        Y轴范围 = max(Y轴范围, 1.0)  # 最小范围为 1

        # 5. 计算缩放比例和 X 轴步长
        Y缩放 = 绘图高度 / Y轴范围 if Y轴范围 != 0 else 1
        X增量 = 绘图宽度 / (PLOT_POINTS - 1) if PLOT_POINTS > 1 else 绘图宽度

        # 6. 绘制 Y 轴刻度和网格线
        Y刻度数 = 5  # 绘制 6 个标签
        for i in range(Y刻度数 + 1):
            值 = Y轴最小值 + (Y轴范围 * i / Y刻度数)
            y = Y结束 - (值 - Y轴最小值) * Y缩放  # 计算 Y 坐标
            if Y起始 - 5 < y < Y结束 + 5:  # 检查是否在可见范围内
                # 绘制刻度短线
                画布.create_line(X起始 - 5, y, X起始, y, fill=PLOT_AXIS_COLOR)
                # 绘制刻度标签
                画布.create_text(X起始 - 10, y, text=f"{值:.1f}", anchor=tk.E, font=("Segoe UI", 7))
                # 绘制水平网格线 (虚线)
                if i > 0:  # 不绘制在 X 轴上的网格线
                    画布.create_line(X起始, y, X结束, y, fill=PLOT_GRID_COLOR, dash=(2, 2))

        # 7. 绘制 X 轴刻度和标签
        X刻度数 = 10  # 大约显示 10 个标签
        X刻度间隔 = max(1, (PLOT_POINTS - 1) // X刻度数 if PLOT_POINTS > 1 else 1)
        for i in range(PLOT_POINTS):
            x = X起始 + i * X增量
            # 每隔一定间隔或最后一个点绘制标签
            if i % X刻度间隔 == 0 or i == PLOT_POINTS - 1:
                # 绘制刻度短线
                画布.create_line(x, Y结束, x, Y结束 + 5, fill=PLOT_AXIS_COLOR)
                # 绘制刻度标签 (数据点索引 1 到 N)
                画布.create_text(x, Y结束 + 10, text=str(i + 1), anchor=tk.N, font=("Segoe UI", 7))

        # 8. 定义内部函数用于绘制单条曲线
        def 绘制曲线(数据, 颜色):
            点列表 = []
            找到有效点 = False  # Track if we've started plotting non-padding data
            for i, 值 in enumerate(数据):
                # Check if the value is valid for plotting
                is_valid_point = isinstance(值, (int, float)) and 值 != 0.0  # Original logic used 0.0 as padding

                # Start accumulating points only after the first valid point is found
                if not 找到有效点 and is_valid_point:
                    找到有效点 = True

                if 找到有效点:
                    if is_valid_point:
                        # Calculate canvas coordinates
                        x = X起始 + i * X增量
                        y_scaled = (值 - Y轴最小值) * Y缩放
                        y = Y结束 - max(0, min(绘图高度, y_scaled))  # Clamp Y within plot area

                        # Add point to the current line segment
                        点列表.extend([x, y])
                    else:
                        # If an invalid point (padding 0.0 or None) is encountered after starting,
                        # draw the segment accumulated so far and reset.
                        if len(点列表) >= 4:  # Need at least 2 points (4 coords)
                            try:
                                画布.create_line(点列表, fill=颜色, width=2, smooth=False)
                            except tk.TclError:
                                pass  # Ignore error if canvas destroyed
                        点列表 = []  # Start new segment

            # Draw the last segment if it contains points
            if len(点列表) >= 4:
                try:
                    画布.create_line(点列表, fill=颜色, width=2, smooth=False)
                except tk.TclError:
                    pass

        # 9. 调用内部函数绘制温度和湿度曲线
        绘制曲线(温度列表, PLOT_TEMP_COLOR)
        绘制曲线(湿度列表, PLOT_HUMI_COLOR)

        # --- 这段绘制最后一个点列表的代码似乎有问题，注释掉 ---
        # if '点列表' in locals() and len(点列表) >= 4:
        #     # fill 使用了湿度列表最后一个值，这很奇怪，应该是颜色
        #     # 而且绘制曲线函数内部已经处理了最后一个段
        #     # 画布.create_line(点列表, fill=湿度列表[-1], width=2, smooth=False) # Draw last segment
        #     pass

        # 10. 绘制图例
        图例Y = Y起始 - 15
        图例X起始 = X起始 + 10
        # 温度图例
        画布.create_line(图例X起始, 图例Y, 图例X起始 + 20, 图例Y, fill=PLOT_TEMP_COLOR, width=2)
        画布.create_text(图例X起始 + 25, 图例Y, text="温度 (°C)", fill=PLOT_TEMP_COLOR, anchor=tk.W,
                         font=("Segoe UI", 8))
        # 湿度图例
        图例X起始 += 100  # 调整水平间距
        画布.create_line(图例X起始, 图例Y, 图例X起始 + 20, 图例Y, fill=PLOT_HUMI_COLOR, width=2)
        画布.create_text(图例X起始 + 25, 图例Y, text="湿度 (%)", fill=PLOT_HUMI_COLOR, anchor=tk.W,
                         font=("Segoe UI", 8))

    def destroy(self):
        """Destroys the Toplevel window."""
        if self.is_active():
            self.top_level.destroy()
        self.top_level = None # Clear reference

    def is_active(self):
         """Checks if the data viewer window currently exists and is valid."""
         return self.top_level is not None and self.top_level.winfo_exists()

    def lift_window(self):
        """Brings the window to the front."""
        if self.is_active():
             self.top_level.lift()
             self.top_level.focus_force()

# --- 主应用类 (拆分行) ---
class ArduinoMonitorApp:
    def __init__(self, 主窗口):
        self.主窗口 = 主窗口
        self.主窗口.title("灯光温湿度监控系统 (含雷达)")
        self.主窗口.geometry("661x629")
        self.主窗口.resizable(False, False)

        # 图片对象存储 (分开写)
        self.背景图片 = None
        self.灯灭图片 = None
        self.灯亮图片 = None
        self.按钮图片 = {}
        self.绘图背景图片 = None

        # 串口相关状态 (分开写)
        self.串口运行中 = False
        self.串口读取线程 = None
        self.arduino串口 = None
        self.串口号 = None

        # 队列
        self.响应队列 = queue.Queue()

        # 数据视图状态 (分开写)
        self.数据视图激活 = False
        self.数据视图任务ID = None

        # 数据库相关 (分开写)
        self.数据库连接 = None
        self.数据库游标 = None

        # 数据视图窗口引用
        self.绘图窗口 = None # 指向 DataViewer 实例 (下面会创建)

        # Socket 客户端状态 (分开写)
        self.客户端socket = None
        self.socket连接中 = False
        self.socket运行中 = False
        self.socket接收线程 = None

        # 雷达状态 (分开写)
        self.radar_window = None
        self.is_radar_mode_active = False
        self.last_alarm_level = 0

        # --- 初始化流程 ---
        self._加载所有图片()
        self._设置背景图片()
        self._设置数据库()
        self._查找并连接Arduino()
        self._创建界面控件()
        self._启动串口读取线程()
        if USE_SOCKET:
            self._启动Socket客户端()

        self.主窗口.after(RESPONSE_POLL_INTERVAL, self._处理响应队列)
        self.主窗口.protocol("WM_DELETE_WINDOW", self._窗口关闭处理)

    # --- 图片处理 ---
    def _加载图片(self, 文件路径, 调整尺寸=None):
        脚本目录 = os.path.dirname(__file__)
        完整路径 = os.path.join(脚本目录, 文件路径)
        if not os.path.exists(完整路径):
            print(f"错误: 图片文件未找到 '{完整路径}'")
            return None
        try:
            图片 = Image.open(完整路径)
            if 调整尺寸:
                图片.thumbnail(调整尺寸, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(图片)
        except Exception as e:
            print(f"加载图片时出错 '{完整路径}': {e}")
            return None

    def _加载所有图片(self):
        """加载所有需要的图片资源"""
        print("正在加载图片资源...")
        self.背景图片 = self._加载图片(BG_IMG_FILENAME)
        self.灯灭图片 = self._加载图片(LIGHT_OFF_IMG_FILENAME, IMAGE_STATUS_SIZE)
        self.灯亮图片 = self._加载图片(LIGHT_ON_IMG_FILENAME, IMAGE_STATUS_SIZE)
        self.绘图背景图片 = self._加载图片(BG_IMG_FILENAME) # For data view window
        按钮文件信息 = {
            'on': BTN_ON_IMG_FILENAME, 'off': BTN_OFF_IMG_FILENAME,
            'temp': BTN_TEMP_IMG_FILENAME, 'humi': BTN_HUM_IMG_FILENAME,
        }
        for 键, 文件名 in 按钮文件信息.items():
            self.按钮图片[键] = self._加载图片(文件名, BUTTON_IMAGE_SIZE)
            if not self.按钮图片[键]:
                 print(f"警告: 按钮图片 '{文件名}' 加载失败。")
        print("图片加载完成。")

    # --- 新增/修正：发送 JSON 数据到 Socket 的辅助方法 ---
    def _send_json_to_socket(self, payload_data): # 参数名改为 payload_data 更清晰
        """
        将 Python 字典（payload）包装后转换为 JSON 字符串，编码后通过 Socket 发送。
        :param payload_data: 要作为 "payload" 发送的 Python 字典。
        :return: True 如果发送尝试成功，False 如果失败。
        """
        if not USE_SOCKET:
            # print("DEBUG: Socket功能未启用，不发送数据。") # 可选
            return False

        if not (self.客户端socket and self.socket连接中):
            # print("DEBUG: _send_json_to_socket - Socket 未连接，无法发送。") # 可选
            # self._更新状态栏("Socket 未连接，无法发送数据。", "orange") # 可选
            return False

        try:
            # 构建完整的发送数据结构
            完整数据 = {
                "deviceId": DEVICE_ID, # 使用类/全局常量 DEVICE_ID
                "timestamp": datetime.datetime.now().isoformat(), # 标准 ISO 8601
                "payload": payload_data # 原始数据作为 payload
            }
            # 转换为 JSON 字符串
            json_payload_str = json.dumps(完整数据)
            # 编码为 UTF-8 字节串，并添加换行符 (服务器端可能按行读取)
            byte_payload = json_payload_str.encode('utf-8') + b'\n'

            # 发送数据
            self.客户端socket.sendall(byte_payload) # sendall 确保全部发送
            # print(f"Socket: 已发送数据: {json_payload_str}") # 可选的成功日志，调试时取消注释
            return True # <--- *** 正确的位置 ***

        except json.JSONDecodeError as json_e: # 虽然是编码，但捕获以防万一
             self._更新状态栏(f"Socket: JSON 编码错误: {json_e}", "red")
             return False
        except (socket.error, BrokenPipeError, ConnectionResetError) as sock_e:
            # 发送失败，通常意味着连接已中断
            # self._更新状态栏(f"Socket: 发送数据失败: {sock_e}", "orange") # 减少日志，让主socket循环处理
            self.socket连接中 = False # 标记连接可能已断开
            return False
        except Exception as e:
            # 其他发送错误
            self._更新状态栏(f"Socket: 发送数据时发生未知错误: {e}", "red")
            return False

    # --- 新增：处理从 Socket 服务器收到的消息 (占位符) ---
    # --- 处理从 Socket 服务器收到的消息 ---
    def _handle_socket_message(self, message_str):
        """
        处理从 Socket 服务器接收到的字符串消息。
        主要功能是将其记录到控制台和 GUI 日志区域。
        :param message_str: 从服务器收到的原始字符串。
        """
        # 1. 在控制台打印收到的原始消息 (用于调试)
        print(f"SOCKET_RX: {message_str}")
        # --- 更实际的场景：解析服务器指令 ---
        try:
            # 尝试将服务器消息解析为 JSON
            # （如果服务器总是发送 JSON）
            server_command = json.loads(message_str)

            if isinstance(server_command, dict) and 'action' in server_command:
                action = server_command.get('action')
                device_id_target = server_command.get('target_device_id') # 服务器可能指定目标设备

                # 检查指令是否针对本客户端 (如果服务器支持多客户端)
                if device_id_target and device_id_target != DEVICE_ID:
                    print(f"服务器指令非针对本机 ({DEVICE_ID})，目标是 {device_id_target}。忽略。")
                    return

                log_message = f"收到服务器指令: {action}"
                if 'params' in server_command:
                    log_message += f" 参数: {server_command['params']}"
                self._更新状态栏(log_message, "magenta") # 使用洋红色标记服务器指令

                # --- 在这里根据 'action' 执行操作 ---
                if action == "REQUEST_SENSOR_DATA":
                    # 服务器请求客户端立即发送一次温湿度数据
                    print("服务器请求传感器数据，准备发送...")
                    self.发送命令(CMD_GET_TEMP)
                    # 延迟一小会再请求湿度，模拟正常流程
                    self.主窗口.after(DATA_VIEW_REQUEST_DELAY_MS, lambda: self.发送命令(CMD_GET_HUMI))
                elif action == "SET_LED_STATUS":
                    status = server_command.get('params', {}).get('status')
                    if status == "ON":
                        print("服务器指令：开灯")
                        self.发送命令(CMD_LIGHT_ON)
                    elif status == "OFF":
                        print("服务器指令：关灯")
                        self.发送命令(CMD_LIGHT_OFF)
                    else:
                        self._更新状态栏(f"服务器指令SET_LED_STATUS参数无效: {status}", "orange")
                elif action == "CONTROL_RADAR":
                    radar_cmd = server_command.get('params', {}).get('command')
                    if radar_cmd == "ON":
                        print("服务器指令：启动雷达")
                        if not self.is_radar_mode_active: # 避免重复打开
                             self._打开雷达窗口() # 这个方法会发送 RADAR_ON
                    elif radar_cmd == "OFF":
                        print("服务器指令：停止雷达")
                        if self.is_radar_mode_active:
                             self._关闭雷达模式() # 这个方法会发送 RADAR_OFF
                    else:
                        self._更新状态栏(f"服务器指令CONTROL_RADAR参数无效: {radar_cmd}", "orange")

                # ... 可以添加更多服务器指令的处理 ...
                else:
                    self._更新状态栏(f"未知的服务器指令动作: {action}", "orange")

            else:
                # 如果不是期望的 JSON 指令格式，就按普通消息处理
                # （这部分可能与 _处理响应队列中的 SOCKET 分支重复，需要协调）
                # 通常，如果 _处理响应队列已经显示了，这里就不需要再次显示原始消息
                # self._更新状态栏(f"服务器消息 (非指令格式): {message_str}", "grey")
                pass # 假设原始消息已由调用者记录

        except json.JSONDecodeError:
            # 如果服务器消息不是 JSON，则按普通文本消息处理
            # （同样，这可能与 _处理响应队列中的 SOCKET 分支重复）
            # self._更新状态栏(f"收到服务器文本消息: {message_str}", "blue")
            print(f"服务器发送非JSON文本消息: {message_str}")
        except Exception as e:
            error_msg = f"处理服务器消息时发生错误: {e}\n原始消息: {message_str}"
            print(error_msg)
            traceback.print_exc() # 打印详细错误堆栈到控制台
            self._更新状态栏(error_msg, "red")

    def _设置背景图片(self):
        """设置主窗口背景图片"""
        if self.背景图片:
            背景标签 = tk.Label(self.主窗口, image=self.背景图片, borderwidth=0)
            背景标签.place(x=0, y=0, relwidth=1, relheight=1)
            背景标签.lower()

    # --- 设置与核心逻辑 ---
    def _设置数据库(self):
        """连接或创建 SQLite 数据库并创建表"""
        try:
            self.数据库连接 = sqlite3.connect(DB_NAME, timeout=10.0, check_same_thread=False)
            self.数据库游标 = self.数据库连接.cursor()
            表结构 = {
                'temperature': 'temp REAL NOT NULL',
                'humidity': 'humi REAL NOT NULL'
            }
        except sqlite3.Error as e:
            messagebox.showerror("数据库错误", f"数据库连接失败: {e}")
            self.主窗口.quit()
            return

        try:
            for 表名, 字段定义 in 表结构.items():
                sql = f'''CREATE TABLE IF NOT EXISTS {表名} (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            {字段定义},
                            t TEXT NOT NULL
                        )'''
                self.数据库游标.execute(sql)
            self.数据库连接.commit()
            print(f"数据库 '{DB_NAME}' 连接成功并检查/创建表完成。")
        except sqlite3.Error as e:
            messagebox.showerror("数据库错误", f"创建表失败: {e}")
            if self.数据库连接:
                 self.数据库连接.close()
            self.主窗口.quit()
        except Exception as e_create:
            messagebox.showerror("未知错误", f"创建数据库表时发生错误: {e_create}")
            if self.数据库连接:
                 self.数据库连接.close()
            self.主窗口.quit()


    def _查找并连接Arduino(self):
        """自动查找可能的 Arduino 端口并尝试连接"""
        print("正在查找 Arduino 端口...")
        可用端口 = serial.tools.list_ports.comports()
        目标端口 = None
        for p in 可用端口:
            # 使用更安全的访问方式，并处理 None 的情况
            desc = p.description or ""
            dev = p.device or ""
            print(f"  检测到端口: {dev} - {desc}")
            if any(k.lower() in desc.lower() or k.lower() in dev.lower() for k in ARDUINO_KEYWORDS):
                目标端口 = p.device
                print(f"  找到可能的 Arduino 端口: {目标端口}")
                break

        if 目标端口:
            try:
                self.arduino串口 = serial.Serial(目标端口, ARDUINO_BAUDRATE, timeout=SERIAL_TIMEOUT)
                time.sleep(2)
            except serial.SerialException as e:
                self._更新状态栏(f"错误: 连接到 {目标端口} 失败: {e}", "red")
                self.arduino串口 = None
                return
            except Exception as e:
                self._更新状态栏(f"错误: 连接时发生未知错误: {e}", "red")
                self.arduino串口 = None
                return

            if self.arduino串口 and self.arduino串口.is_open: # Double check after creation
                self.串口号 = 目标端口
                self._更新状态栏(f"成功连接到 Arduino ({self.串口号})")
            else: # Should not happen if Serial() succeeded, but good practice
                self.arduino串口 = None
                self._更新状态栏("错误: 无法打开串口。", "red")
        else:
            self._更新状态栏("错误: 未找到 Arduino 端口。请检查连接和驱动。", "red")
            self.arduino串口 = None

    def _创建界面控件(self):
        """创建主窗口的所有 GUI 控件"""
        # 灯光状态图片
        self.灯光状态标签 = tk.Label(self.主窗口, image=self.灯灭图片 if self.灯灭图片 else None, text="" if self.灯灭图片 else "灯光图片加载失败", fg="red", borderwidth=0, highlightthickness=0)
        self.灯光状态标签.place(x=40, y=30)

        # 控制按钮
        起始X = IMAGE_STATUS_SIZE[0] + 60
        按钮Y = 65
        按钮间距 = 15
        按钮配置 = [ ('on', CMD_LIGHT_ON), ('off', CMD_LIGHT_OFF), ('temp', CMD_GET_TEMP), ('humi', CMD_GET_HUMI) ]
        当前X = 起始X
        for 键, 命令 in 按钮配置:
            图片 = self.按钮图片.get(键)
            cmd_func = lambda c=命令: self.发送命令(c)
            if 图片:
                btn = tk.Button(self.主窗口, image=图片, command=cmd_func, bd=0, highlightthickness=0, relief=tk.FLAT, cursor="hand2", activebackground=self.主窗口.cget('bg'))
                btn_width = 图片.width()
                btn_height = 图片.height()
            else:
                btn = ttk.Button(self.主窗口, text=键.upper(), command=cmd_func)
                btn_width = BUTTON_IMAGE_SIZE[0]
                btn_height = BUTTON_IMAGE_SIZE[1]
            btn.place(x=当前X, y=按钮Y, width=btn_width, height=btn_height)
            当前X += btn_width + 按钮间距

        # 温湿度数据显示标签
        数据标签Y起始 = 按钮Y + BUTTON_IMAGE_SIZE[1] + 40
        数据标签X = 起始X
        标签字体 = ("微软雅黑", 11)
        数值字体 = ("微软雅黑", 11, "bold")
        self.数值标签 = {}
        标签信息 = [ ("当前温度:", "temp", "-- °C"), ("当前湿度:", "humi", "-- %") ]
        当前Y = 数据标签Y起始
        for 文本, 键, 默认值 in 标签信息:
            tk.Label(self.主窗口, text=文本, font=标签字体, fg="#333").place(x=数据标签X, y=当前Y, anchor='w')
            self.数值标签[键] = tk.Label(self.主窗口, text=默认值, font=数值字体, fg="#00529B")
            self.数值标签[键].place(x=数据标签X + 90, y=当前Y, anchor='w')
            当前Y += 35

        # 数据视图和雷达按钮
        控制按钮Y = 当前Y + 15
        按钮总宽度 = (当前X - 起始X - 按钮间距) # Calculate width based on buttons above
        单个按钮宽度 = max(100, (按钮总宽度 - 按钮间距) / 2) # Distribute width, min 100
        控制按钮高度 = 32
        初始状态 = tk.NORMAL if (self.arduino串口 and self.arduino串口.is_open) else tk.DISABLED

        self.数据视图按钮 = ttk.Button(self.主窗口, text="数据视图显示", command=self._切换数据视图, state=初始状态)
        self.数据视图按钮.place(x=数据标签X, y=控制按钮Y, width=单个按钮宽度, height=控制按钮高度)

        self.雷达扫描按钮 = ttk.Button(self.主窗口, text="雷达扫描", command=self._打开雷达窗口, state=初始状态)
        self.雷达扫描按钮.place(x=数据标签X + 单个按钮宽度 + 按钮间距, y=控制按钮Y, width=单个按钮宽度, height=控制按钮高度)

        # 底部日志文本框
        日志Y偏移 = 180
        日志高度 = 150
        self.日志文本框 = scrolledtext.ScrolledText(self.主窗口, height=1, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9), borderwidth=1, relief=tk.SUNKEN)
        self.日志文本框.place(relx=0.5, rely=1.0, y=-日志Y偏移, anchor="center", relwidth=0.9, height=日志高度)

    # --- 线程与串口 ---
    def _启动串口读取线程(self): # ... (内容不变) ...
        if self.arduino串口 and self.arduino串口.is_open: self.串口运行中 = True; self.串口读取线程 = threading.Thread(target=self._读取串口数据, daemon=True); self.串口读取线程.start(); print("串口读取线程已启动。")
        else: print("串口未连接，无法启动读取线程。")
    def _读取串口数据(self): # ... (内容不变, 包含雷达判断) ...
        print("串口读取线程任务已启动。")
        while self.串口运行中:
            if not (self.arduino串口 and self.arduino串口.is_open): time.sleep(1); continue
            try:
                if (self.arduino串口.in_waiting > 0):
                    响应 = self.arduino串口.readline().decode('utf-8', errors='ignore').strip()
                    if 响应:
                        # Simple check for potential radar data "angle,distance"
                        is_radar_like = False
                        if ',' in 响应:
                            parts = 响应.split(',')
                            if len(parts) == 2:
                                try: float(parts[0]); float(parts[1]); is_radar_like = True
                                except ValueError: pass # Not two numbers
                        # Route data based on format and radar mode
                        if is_radar_like:
                            if self.is_radar_mode_active: self.响应队列.put(("RADAR_DATA", 响应))
                        else: self.响应队列.put(("SERIAL", 响应))
            except serial.SerialException as e:
                if self.串口运行中:
                    self.响应队列.put(("ERROR", f"SerialException - {e}"))
                    try:
                        self.arduino串口.close()
                    except Exception:
                        pass
                    self.arduino串口 = None
                break
            except Exception as e:
                if self.串口运行中: self.响应队列.put(("ERROR", f"Exception - {e}"))
                break
            time.sleep(0.01) # Slightly shorter sleep for responsiveness
        self.串口运行中 = False; print("串口读取线程任务已结束。")

    # --- Socket 客户端 ---
    def _启动Socket客户端(self): # ... (内容不变) ...
        if not USE_SOCKET: return;
        if self.socket连接中: print("Socket 客户端已在运行。"); return
        print("准备启动 Socket 客户端线程..."); self.socket运行中 = True
        self.socket接收线程 = threading.Thread(target=self._socket连接和接收任务, daemon=True); self.socket接收线程.start()
    def _socket连接和接收任务(self): # ... (内容不变) ...
        print("Socket 客户端线程已启动，开始连接...")
        while self.socket运行中:
            sock = None
            try:
                self._更新状态栏("Socket: 正在尝试连接...", "blue"); sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(SOCKET_TIMEOUT); sock.connect((SERVER_IP, SERVER_PORT))
                self.客户端socket = sock; self.socket连接中 = True; self._更新状态栏(f"Socket: 连接成功", "green")
                # connect_msg = f"GUI客户端已连接 @ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"; try: self.客户端socket.sendall(connect_msg.encode('utf-8') + b'\n'); except Exception as send_e: self._更新状态栏(f"Socket: 发送初始消息失败: {send_e}", "orange")
                while self.socket运行中 and self.socket连接中:
                    try:
                        self.客户端socket.settimeout(1.0); 数据 = self.客户端socket.recv(1024)
                        if not 数据: self._更新状态栏("Socket: 服务器关闭连接。", "orange"); self.socket连接中 = False; break
                        消息 = 数据.decode('utf-8', errors='ignore').strip();
                        if 消息: self.响应队列.put(("SOCKET", 消息))
                    except socket.timeout: continue
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.error) as conn_e: self._更新状态栏(f"Socket: 连接中断: {conn_e}", "red"); self.socket连接中 = False; break
                    except Exception as recv_e: self._更新状态栏(f"Socket: 接收出错: {recv_e}", "red"); self.socket连接中 = False; break
            except socket.timeout: self._更新状态栏(f"Socket: 连接超时", "orange")
            except ConnectionRefusedError: self._更新状态栏(f"Socket: 连接被拒绝", "red")
            except socket.gaierror: self._更新状态栏(f"Socket: 无法解析地址", "red")
            except Exception as e: self._更新状态栏(f"Socket: 连接未知错误: {e}", "red")
            if sock:
                try:
                    sock.close()
                except:
                    pass
                self.客户端socket = None
                self.socket连接中 = False
            if not self.socket运行中: break
            self._更新状态栏(f"Socket: {SOCKET_RECONNECT_INTERVAL} 秒后重连...", "orange")
            for _ in range(SOCKET_RECONNECT_INTERVAL):
                 if not self.socket运行中: break; time.sleep(1)
            if not self.socket运行中: break
        print("Socket 客户端线程已停止。"); self.客户端socket = None; self.socket连接中 = False
    def _停止Socket客户端(self): # ... (内容不变) ...
        if not USE_SOCKET: return; print("正在停止 Socket 客户端..."); self.socket运行中 = False
        if self.客户端socket:
            print("尝试关闭活动的 Socket 连接..."); sock_to_close = self.客户端socket; self.客户端socket = None; self.socket连接中 = False
            try:
                sock_to_close.shutdown(socket.SHUT_RDWR)
            except (OSError, socket.error):
                pass
            except Exception as e:
                print(f"Socket shutdown error: {e}")
            try:
                sock_to_close.close()
                print("Socket 连接已关闭。")
            except Exception as e:
                print(f"关闭 Socket close 时出错: {e}")
        self.客户端socket = None; self.socket连接中 = False

    # --- 响应处理 ---
    def _解析响应(self, 响应字符串): # ... (内容不变) ...
        数据字典 = {}; 部分列表 = [部分 for 部分 in 响应字符串.split(';') if 部分];
        for 部分 in 部分列表:
            if '=' in 部分:
                try: 键, 值 = 部分.split('=', 1); 数据字典[键.strip()] = 值.strip()
                except ValueError: print(f"警告: 解析响应部分格式无效: '{部分}'")
        return 数据字典

    def _处理响应队列(self):
        """定时从队列中获取并处理所有类型的消息"""
        try:
            while True:
                来源, 消息体 = self.响应队列.get_nowait()

                if 来源 == "ERROR":
                    # ... (错误处理保持不变) ...
                    错误信息 = 消息体
                    self._更新状态栏(f"后台错误: {错误信息}", "red")
                    if "SerialException" in 错误信息 and self.arduino串口 is None:
                        self._处理断开连接()

                elif 来源 == "SERIAL":
                    # ... (处理普通 SERIAL 响应保持不变) ...
                    if 消息体.startswith("OK ") or 消息体.startswith("ERR ") or 消息体.startswith("INFO "): # 处理确认信息
                        print(f"收到 Arduino 确认/信息: {消息体}")
                        self._更新状态栏(f"Arduino 响应: {消息体}")
                    else:
                        数据 = self._解析响应(消息体)
                        if 数据:
                            self._处理传感器数据(数据, 数据.get('command')) # 处理键值对数据

                elif 来源 == "RADAR_DATA":
                    # 当收到雷达数据时
                    angle, dist = None, None # 初始化
                    try:
                        angle_str, dist_str = 消息体.split(',')
                        angle = float(angle_str)
                        dist_float = float(dist_str)
                        # 转换 Arduino 的无效标记为 None
                        if dist_float >= RADAR_INVALID_MARKER:
                             dist = None
                        else:
                             dist = dist_float
                    except ValueError:
                        print(f"警告: 无法解析雷达数据: {消息体}")
                        dist = None # 解析失败也视为无效
                    except Exception as e:
                        print(f"处理雷达数据时出错: {e}")
                        dist = None

                    # --- 更新雷达窗口 (如果存在) ---
                    if self.is_radar_mode_active and self.radar_window and self.radar_window.top_level.winfo_exists():
                        if angle is not None: # 确保角度有效
                            self.radar_window.update_radar_data(angle, dist) # 传递原始解析或 None

                    # <<< 新增：计算并发送报警级别 >>>
                    current_alarm_level = 0 # 默认级别 0 (关)
                    if dist is not None and 0 < dist <= 100: # 检查距离有效且在报警范围内
                        if dist <= 30:       # 0 < dist <= 30
                            current_alarm_level = 3 # 快
                        elif dist <= 60:     # 30 < dist <= 60
                            current_alarm_level = 2 # 中
                        else:                # 60 < dist <= 100
                            current_alarm_level = 1 # 慢

                    # 仅当报警级别发生变化时发送命令
                    if current_alarm_level != self.last_alarm_level:
                        alarm_command = f"{CMD_ALARM_PREFIX}{current_alarm_level}\n" # 构建命令 "ALARM X\n"
                        if self.发送命令(alarm_command): # 发送命令
                            self.last_alarm_level = current_alarm_level # 更新 Python 端记录的级别
                            self._更新状态栏(f"设置报警级别: {current_alarm_level}", "orange")
                        else:
                             # 发送失败的处理 (可选)
                             print(f"发送 ALARM 命令失败: {alarm_command.strip()}")
                    # <<< 结束新增报警逻辑 >>>

                    # --- 发送雷达数据到 Socket (如果启用) ---
                    if USE_SOCKET and self.客户端socket and self.socket连接中:
                        # 只有在距离有效时才发送
                        if dist is not None and angle is not None:
                             radar_payload = {"type": "radar", "angle": angle, "distance": round(dist, 1)}
                             self._send_json_to_socket(radar_payload)

                elif 来源 == "SOCKET":
                    # ... (处理 SOCKET 消息保持不变) ...
                    self._更新状态栏(f"服务器消息: {消息体}", "blue")
                    self._handle_socket_message(消息体)

                elif 来源 == "SOCKET_STATUS":
                    # ... (处理 SOCKET_STATUS 保持不变) ...
                     level = 消息体.split('] ', 1)[0][1:]; text = 消息体.split('] ', 1)[1]; color = "blue" if level=="INFO" else ("orange" if level=="WARN" else ("red" if level=="ERROR" else "green"))
                     self._更新状态栏(f"Socket: {text}", color)

        except queue.Empty:
            pass
        except Exception as e:
            print(f"处理响应队列时发生错误: {e}")
            traceback.print_exc()
            self._更新状态栏(f"严重错误: 处理响应队列失败: {e}", "red")
        finally:
            if hasattr(self, '主窗口') and self.主窗口.winfo_exists():
                 self.主窗口.after(RESPONSE_POLL_INTERVAL, self._处理响应队列)


    def _处理传感器数据(self, 数据, 命令):
        """处理从 Arduino 获取到的传感器数据或状态响应 (修正 elif 位置)"""
        print(f"DEBUG: _处理传感器数据 收到数据: {数据}, 命令: {命令}")

        # --- 首先处理灯光状态响应 ---
        灯光状态 = 数据.get('light')
        if 命令 == 'arduino1' and 灯光状态 == 'on':
            if hasattr(self, '灯亮图片') and self.灯亮图片 and hasattr(self, '灯光状态标签') and self.灯光状态标签.winfo_exists():
                 try:
                     self.灯光状态标签.config(image=self.灯亮图片)
                 except tk.TclError:
                     print("DEBUG: 更新灯亮图片时 TclError")
            else: print("DEBUG: 无法更新灯亮图片")
            self._更新状态栏("灯光已打开 (已确认)")
            return
        elif 命令 == 'arduino2' and 灯光状态 == 'off':
             if hasattr(self, '灯灭图片') and self.灯灭图片 and hasattr(self, '灯光状态标签') and self.灯光状态标签.winfo_exists():
                 try:
                     self.灯光状态标签.config(image=self.灯灭图片)
                 except tk.TclError:
                     print("DEBUG: 更新灯灭图片时 TclError")
             else: print("DEBUG: 无法更新灯灭图片")
             self._更新状态栏("灯光已关闭 (已确认)")
             return

        # --- 如果不是灯光响应，再处理温湿度或错误 ---
        是否温度 = (命令 == 'arduino3')
        传感器键 = 'temp' if 是否温度 else 'humi'
        数据库表名 = 'temperature' if 是否温度 else 'humidity'
        标签对象 = self.数值标签.get(传感器键)
        单位 = "°C" if 是否温度 else "%"
        名称 = "温度" if 是否温度 else "湿度"

        # --- 主要逻辑块1：检查是否存在传感器键 ---
        if 传感器键 in 数据:
            try:
                数值 = float(数据[传感器键])
                # 处理有效数值...
                if 标签对象:
                    标签对象.config(text=f"{数值:.1f} {单位}")
                if self.数据视图激活 and self.绘图窗口 and self.绘图窗口.is_active():
                    if 是否温度: self.绘图窗口.update_gauges(temp=数值)
                    else: self.绘图窗口.update_gauges(humi=数值)
                if USE_SOCKET and self.数据视图激活 and self.客户端socket and self.socket连接中:
                    if not math.isnan(数值):
                         env_json = {"type": 传感器键, "value": 数值, "unit": 单位}
                         self._send_json_to_socket(env_json) # Assuming this helper exists
                if not math.isnan(数值):
                     self._插入传感器数据(数据库表名, 传感器键, 数值)

            except ValueError:
                # 处理数值转换错误
                self._更新状态栏(f"无法解析{名称}值: '{数据[传感器键]}'", "orange")
                if 标签对象: 标签对象.config(text="解析错误")
            except Exception as e:
                # 处理其他可能的错误
                self._更新状态栏(f"处理{名称}数据时出错: {e}", "red")
        # --- 主要逻辑块2：如果不存在传感器键，检查是否存在错误键 ---
        # *** 注意这里的 elif 与上面的 if 对齐 ***
        elif 'error' in 数据:
            错误详情 = 数据['error']
            self._更新状态栏(f"获取{名称}失败: {错误详情}", "orange")
            if 标签对象:
                标签对象.config(text="读取失败")
            # 重置仪表盘
            if self.数据视图激活 and self.绘图窗口 and self.绘图窗口.is_active():
                if 是否温度:
                    self.绘图窗口.update_gauges(temp=None)
                else:
                    self.绘图窗口.update_gauges(humi=None)
        # --- 可以选择添加一个 else 来处理既没有传感器键也没有 error 键的情况 ---
        # else:
        #     print(f"DEBUG: 收到未知格式的传感器响应: {数据}")
        #     self._更新状态栏(f"收到未知响应 (命令={命令})", "grey")

    # --- 数据视图控制 (基本不变) ---
    def _请求数据并更新绘图(self): # ... (内容不变) ...
        if not self.数据视图激活: return;
        if not (self.arduino串口 and self.arduino串口.is_open): self._更新状态栏("DV: Arduino disconnected", "orange"); self._关闭数据视图(); return
        if not self.发送命令(CMD_GET_TEMP): self._关闭数据视图(); return
        self.数据视图任务ID = self.主窗口.after(DATA_VIEW_REQUEST_DELAY_MS, self._请求湿度并安排下一次完整循环)
    def _请求湿度并安排下一次完整循环(self): # ... (内容不变) ...
        if not self.数据视图激活: return
        if not (self.arduino串口 and self.arduino串口.is_open): self._更新状态栏("DV: Arduino disconnected", "orange"); self._关闭数据视图(); return
        if not self.发送命令(CMD_GET_HUMI): self._关闭数据视图(); return
        下次延迟 = max(100, DATA_VIEW_INTERVAL_MS - DATA_VIEW_REQUEST_DELAY_MS); self.数据视图任务ID = self.主窗口.after(下次延迟, self._请求数据并更新绘图)
    def _切换数据视图(self): # ... (内容不变, 使用 self.绘图窗口=...) ...
         if self.数据视图激活: self._关闭数据视图()
         else:
             if not (self.arduino串口 and self.arduino串口.is_open): messagebox.showerror("错误", "Arduino 未连接。"); return
             self.数据视图激活 = True; self.数据视图按钮.config(text="关闭数据视图"); self._更新状态栏("数据视图已开启。", "green")
             self._显示历史曲线和仪表窗口(); self._启动Socket客户端()
             if self.数据视图任务ID:
                 try:
                     self.主窗口.after_cancel(self.数据视图任务ID)
                 except ValueError:
                     pass
                 except Exception:
                     pass
                 self.数据视图任务ID = None
             self.数据视图任务ID = self.主窗口.after(100, self._请求数据并更新绘图)

    def _关闭数据视图(self):
        """停止数据视图相关的所有活动：定时任务、Socket、绘图窗口"""
        # *** 修改检查条件: 使用 is_active() ***
        # Check if already closing or closed
        # if not self.数据视图激活 and not self.数据视图任务ID and self.绘图窗口 is None and not self.socket运行中:
        if not self.数据视图激活:  # Simpler check: if the flag says it's not active, assume closed/closing
            # print("DEBUG: _关闭数据视图 - Already inactive.") # Optional
            # Ensure references are cleared if somehow left over
            if self.绘图窗口: self.绘图窗口 = None
            if self.数据视图任务ID:
                try: self.主窗口.after_cancel(self.数据视图任务ID);
                except: pass;
            self.数据视图任务ID = None
            return

        print("正在关闭数据视图...")

        # 1. Stop scheduled tasks
        if self.数据视图任务ID:
            try:
                self.主窗口.after_cancel(self.数据视图任务ID)
                print("已取消数据视图定时任务。")
            except ValueError:
                pass  # Ignore error if task ID is invalid
            except Exception as e:
                print(f"取消 after 任务时出错: {e}")  # Log other errors
            self.数据视图任务ID = None

        # 2. Stop socket client (if used and running)
        self._停止Socket客户端()  # This method should handle checks internally

        # 3. Update state flag FIRST
        self.数据视图激活 = False

        # 4. Close and clean up the viewer window instance
        # *** 修改检查条件: 使用 is_active() ***
        # if self.绘图窗口 and self.绘图窗口.winfo_exists():
        if self.绘图窗口 and self.绘图窗口.is_active():  # <<< 使用 is_active()
            try:
                print("DEBUG: 正在调用 self.绘图窗口.destroy()")
                self.绘图窗口.destroy()  # Call the viewer's destroy method
                print("DEBUG: DataViewer destroy() 已调用。")
            except Exception as e:
                print(f"销毁 DataViewer 时发生错误: {e}")
        # Clear the reference regardless of success/failure of destroy
        self.绘图窗口 = None
        print("绘图窗口引用已清理。")

        # 5. Update main window button state
        # Check if main GUI components still exist
        if hasattr(self, '数据视图按钮') and self.数据视图按钮.winfo_exists():
            try:
                状态 = tk.NORMAL if (self.arduino串口 and self.arduino串口.is_open) else tk.DISABLED
                self.数据视图按钮.config(text="数据视图显示", state=状态)
            except tk.TclError:
                pass  # Ignore if button destroyed

        # 6. Update status bar
        if self.arduino串口 and self.arduino串口.is_open:
            # Only log 'closed' if Arduino still connected
            self._更新状态栏("数据视图已关闭。", "orange")
        print("数据视图关闭完成。")

    # --- Arduino 断开处理 (基本不变) ---
    def _处理断开连接(self): # ... (内容基本不变，确保按钮状态更新) ...
        print("检测到 Arduino 断开连接，正在处理...");
        # 确保关闭雷达模式（如果激活），这也将尝试发送 ALARM 0
        if self.is_radar_mode_active and self.radar_window:
             print("Arduino断开时雷达模式激活，尝试关闭雷达窗口...")
             # 直接调用雷达窗口的关闭处理可能更好，它会回调 _关闭雷达模式
             try:
                 if self.radar_window.top_level and self.radar_window.top_level.winfo_exists():
                     self.radar_window._handle_close() # 触发雷达窗口关闭和回调
             except Exception as e:
                 print(f"关闭雷达窗口时出错: {e}")
                 # 即使窗口关闭失败，也要继续清理
                 self._关闭雷达模式() # 确保状态和命令被发送

        if self.数据视图激活: print("数据视图处于激活状态，将执行关闭..."); self._关闭数据视图()

        # 更新按钮状态
        if hasattr(self, '数据视图按钮') and self.数据视图按钮.winfo_exists(): self.数据视图按钮.config(state=tk.DISABLED)
        if hasattr(self, '雷达扫描按钮') and self.雷达扫描按钮.winfo_exists(): self.雷达扫描按钮.config(state=tk.DISABLED)
        # 将来可能需要禁用更多按钮...

        if hasattr(self, '数值标签'):
             if 'temp' in self.数值标签: self.数值标签['temp'].config(text="-- °C")
             if 'humi' in self.数值标签: self.数值标签['humi'].config(text="-- %")
        self._更新状态栏("Arduino 连接已断开。", "red")
        # 清理串口对象
        if self.arduino串口:
             try: self.arduino串口.close()
             except: pass
             self.arduino串口 = None

    # --- 绘图功能 (基本不变, 但使用 self.绘图窗口) ---
    def _获取历史数据(self, 需要完整数据=False): # ... (内容不变) ...
        温度列表 = []; 湿度列表 = [];
        if not (self.数据库连接 and self.数据库游标): messagebox.showerror("数据库错误", "数据库未连接..."); return None, None
        try: self.数据库游标.execute("SELECT temp FROM temperature ORDER BY id DESC LIMIT ?", (PLOT_POINTS,)); 温度列表 = [r[0] for r in self.数据库游标.fetchall() if r[0] is not None]; 温度列表.reverse()
        except sqlite3.Error as e: messagebox.showerror("数据库错误", f"读取温度失败: {e}"); return None, None
        try: self.数据库游标.execute("SELECT humi FROM humidity ORDER BY id DESC LIMIT ?", (PLOT_POINTS,)); 湿度列表 = [r[0] for r in self.数据库游标.fetchall() if r[0] is not None]; 湿度列表.reverse()
        except sqlite3.Error as e: messagebox.showerror("数据库错误", f"读取湿度失败: {e}"); return None, None
        if 需要完整数据 and (len(温度列表) < PLOT_POINTS or len(湿度列表) < PLOT_POINTS): print("历史数据不足..."); return None, None
        if not 需要完整数据: 温度列表 = ([0.0] * (PLOT_POINTS - len(温度列表)) + 温度列表); 湿度列表 = ([0.0] * (PLOT_POINTS - len(湿度列表)) + 湿度列表)
        return 温度列表, 湿度列表
    def _显示历史曲线和仪表窗口(self): # ... (内容不变, 实例化 DataViewer) ...
        if self.绘图窗口 and self.绘图窗口.is_active(): self.绘图窗口.lift_window(); return # Use DataViewer method
        try:
            # 创建 DataViewer 实例，它会自己创建 Toplevel 窗口
            self.绘图窗口 = DataViewer(self.主窗口, self.数据库连接, self._关闭数据视图) # Pass close callback
            # 初始化仪表盘值
            initial_temp, initial_humi = None, None
            if hasattr(self,'数值标签'):
                try: initial_temp = float(self.数值标签['temp'].cget("text").split()[0])
                except: pass
                try: initial_humi = float(self.数值标签['humi'].cget("text").split()[0])
                except: pass
            self.绘图窗口.update_gauges(temp=initial_temp, humi=initial_humi)
        except Exception as e: print(f"打开数据视图时出错: {e}"); messagebox.showerror("错误", f"无法打开数据视图:\n{e}"); self.绘图窗口 = None; self._关闭数据视图() # Ensure state is reset

    def _绘图窗口关闭处理(self): # ... (现在由 DataViewer 管理, 这个方法可以简化或移除) ...
        print("正在清理绘图窗口引用..."); # Main app only needs to clear the reference
        self.绘图窗口 = None; # Viewer handles its own destroy
        print("绘图窗口引用清理完成。")
    def _更新绘图(self):
        """获取最新历史数据并触发 DataViewer 重绘历史曲线图"""
        # *** 修改检查条件: 使用 is_active() ***
        # if not (self.绘图窗口 and self.历史曲线画布 and self.绘图窗口.winfo_exists()):
        if not (self.数据视图激活 and self.绘图窗口 and self.绘图窗口.is_active()):
            # print("DEBUG: _更新绘图 skipped, DataViewer not active.") # Debug log
            return

        # 调用 DataViewer 实例的方法来重绘其内部的历史图
        # DataViewer 的 redraw_history_plot 内部会获取数据并绘图
        try:
            self.绘图窗口.redraw_history_plot()
        except Exception as e:
            print(f"调用 DataViewer 重绘历史图时出错: {e}")
            # 可以考虑在此处关闭数据视图或记录更严重的错误
            # self._关闭数据视图()

    def _插入传感器数据(self, 表名, 列名, 值):
        """将传感器数据插入数据库，并在成功后触发绘图更新 (已修正窗口检查)"""
        if not (self.数据库连接 and self.数据库游标):
            print(f"数据库未连接，无法插入 {表名} 数据。")
            return False # Indicate failure

        try:
            当前时间 = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql = f"INSERT INTO {表名} ({列名}, t) VALUES (?, ?)"
            self.数据库游标.execute(sql, (值, 当前时间))
            self.数据库连接.commit()
            print(f"数据库插入: {表名} - {值:.1f} @ {当前时间}") # 移除单位

            # --- 数据插入成功后，触发历史曲线图更新 ---
            # *** 修改检查条件: 使用 is_active() ***
            # if self.数据视图激活 and self.绘图窗口 and self.绘图窗口.winfo_exists():
            if self.数据视图激活 and self.绘图窗口 and self.绘图窗口.is_active():
                # 使用 after 确保更新在主线程执行
                self.主窗口.after(0, self._更新绘图) # Trigger plot update in main loop
            return True

        except sqlite3.Error as e:
            错误信息 = f"数据库错误 ({表名} 插入失败): {e}"
            print(错误信息)
            self._更新状态栏(错误信息, "red")
            return False # Indicate failure
        except Exception as e:
             错误信息 = f"插入数据到 {表名} 时发生未知错误: {e}"
             print(错误信息)
             self._更新状态栏(错误信息, "red")
             return False # Indicate failure

    # --- Status/Log Update (保持不变) ---
    def _更新状态栏(self, 消息, 颜色="black"): # *** Kept direct update ***
        # ... (内容不变) ...
        当前时间 = datetime.datetime.now().strftime("%H:%M:%S"); 完整消息 = f"[{当前时间}] {消息}\n";
        if hasattr(self, '日志文本框') and self.日志文本框 and self.日志文本框.winfo_exists():
            try: self.日志文本框.config(state=tk.NORMAL); self.日志文本框.insert(tk.END, 完整消息); self.日志文本框.see(tk.END); self.日志文本框.config(state=tk.DISABLED)
            except tk.TclError: pass
            except Exception as e: print(f"(日志更新未知错误) {完整消息.strip()} Error: {e}")
        else: print(f"(日志控件不可用) {完整消息.strip()}")

    # --- Command Sending (保持不变) ---
    def 发送命令(self, 命令):
        """向 Arduino 发送命令"""
        # 检查串口是否已连接
        if not (self.arduino串口 and self.arduino串口.is_open):
            错误消息 = "错误: Arduino 未连接，无法发送命令。"
            print(错误消息)
            self._更新状态栏(错误消息, "red")
            messagebox.showwarning("未连接", "Arduino 未连接，请检查设备连接。")
            self._处理断开连接() # 触发断开处理
            return False # 返回发送失败

        try:
            # 确保命令以换行符结束
            if not 命令.endswith('\n'):
                 命令 += '\n'
            # 将命令字符串编码为字节串并发送
            self.arduino串口.write(命令.encode('utf-8'))
            # self._更新状态栏(f"发送命令: {命令.strip()}") # Optional log
            return True # 返回发送成功

        except serial.SerialTimeoutException:
            # 处理写超时错误
            错误消息 = f"发送命令超时: {命令.strip()}"
            print(错误消息)
            self._更新状态栏(错误消息, "orange")
            messagebox.showwarning("超时", "发送命令到 Arduino 超时。")
            return False # 返回发送失败

        except serial.SerialException as e:
            # 处理严重的串口错误（如设备拔出）
            # --- 修正开始 ---
            错误消息 = f"发送命令失败: {e}"
            print(错误消息)
            self._更新状态栏(错误消息, "red")
            messagebox.showerror("串口错误", f"发送命令时出错: {e}")
            # 尝试关闭已失效的串口对象
            try:
                if self.arduino串口 and self.arduino串口.is_open:
                    self.arduino串口.close()
                    print("因发送错误，串口已关闭。")
            except Exception as close_e:
                print(f"尝试关闭错误串口时发生额外错误: {close_e}")
                pass # 忽略关闭时的错误
            # 标记串口为 None
            self.arduino串口 = None
            # 更新状态栏和处理断开连接
            self._更新状态栏("连接已断开。", "red")
            self._处理断开连接()
            return False # 返回发送失败
            # --- 修正结束 ---

        except Exception as e:
             # 处理其他未知错误
             错误信息 = f"发送命令时发生未知错误: {e}"
             print(错误信息)
             self._更新状态栏(错误信息, "red")
             messagebox.showerror("错误", f"发送命令时发生未知错误: {e}")
             return False # 返回发送失败
    # --- Radar Window Callbacks (保持不变) ---
        # --- Radar Window Callbacks ---
    def _打开雷达窗口(self):
        """处理“雷达扫描”按钮点击事件，打开雷达窗口并启动雷达"""
        # 1. 检查 Arduino 连接
        if not (self.arduino串口 and self.arduino串口.is_open):
            messagebox.showerror("错误", "Arduino 未连接，无法启动雷达扫描。")
            return

        # 2. 检查雷达窗口是否已存在
        if self.radar_window and self.radar_window.top_level.winfo_exists():
            print("雷达窗口已打开。将其置顶。")
            self.radar_window.lift_window()  # 将窗口提到最前
            return

        # 3. 发送 RADAR_ON 命令
        print("正在启动雷达并打开窗口...")
        if self.发送命令(CMD_RADAR_ON):  # 发送命令启动 Arduino 雷达
            # 4. 如果命令发送成功
            self.is_radar_mode_active = True  # 设置雷达模式激活标志
            self.last_alarm_level = 0  # 重置报警级别状态
            # 5. 创建 RadarWindow 实例
            #    传入主窗口、发送命令的回调、关闭雷达模式的回调
            self.radar_window = RadarWindow(self.主窗口, self.发送命令, self._关闭雷达模式)
            self._更新状态栏("雷达扫描已启动。", "blue")
        else:
            # 6. 如果命令发送失败
            messagebox.showerror("错误", "发送 RADAR_ON 指令到 Arduino 失败。\n请检查 Arduino 连接和状态。")
            self.is_radar_mode_active = False  # 确保状态未激活

    def _关闭雷达模式(self):  # <<< 修改：添加发送 ALARM 0 >>>
        print("正在关闭雷达模式...");
        needs_command_sent = False
        if self.is_radar_mode_active:  # 先改变状态标志，避免重入
            needs_command_sent = True
            self.is_radar_mode_active = False  # 更新状态

        # 确保发送 RADAR_OFF 和 ALARM 0
        if needs_command_sent:
            if self.发送命令(CMD_RADAR_OFF):
                self._更新状态栏("雷达扫描已停止。", "orange")
            else:
                self._更新状态栏("发送 RADAR_OFF 指令失败。", "orange")
            # 无论 RADAR_OFF 是否成功，都尝试关闭报警
            if self.发送命令(f"{CMD_ALARM_PREFIX}0\n"):  # 发送 ALARM 0
                self._更新状态栏("报警已停止。", "orange")
                self.last_alarm_level = 0  # 重置 Python 状态
            else:
                self._更新状态栏("发送 ALARM 0 指令失败。", "orange")

        # 清理窗口引用 (可以在 _handle_close 回调之后做)
        # 但为了确保状态一致，这里也清一下
        if self.radar_window:
            # 不需要在这里 destroy，窗口的 WM_DELETE_WINDOW 会处理
            self.radar_window = None  # 清除引用

    # <<< 新增或确保存在：主窗口关闭处理方法 >>>
    def _窗口关闭处理(self):
        """应用程序主窗口关闭时执行的清理操作"""
        print("正在关闭应用程序...")

        # 1. 尝试关闭雷达模式（如果激活），这会发送 RADAR_OFF 和 ALARM 0
        if self.is_radar_mode_active and self.radar_window:
            print("步骤 1a: 关闭雷达窗口和模式...")
            # 调用雷达窗口的关闭处理，它会回调 _关闭雷达模式
            try:
                if self.radar_window.top_level and self.radar_window.top_level.winfo_exists():
                    self.radar_window._handle_close()
            except Exception as e:
                print(f"关闭雷达窗口时出错: {e}")
                # 即使窗口关闭失败，也尝试发送命令
                self._关闭雷达模式()
        elif self.is_radar_mode_active:  # 窗口不存在但模式激活？尝试直接关闭模式
            print("步骤 1b: 雷达模式激活但窗口不存在，尝试关闭模式...")
            self._关闭雷达模式()
        else:
            # 即使雷达模式未激活，也最好发一次 ALARM 0，确保蜂鸣器关闭
            print("步骤 1c: 发送最终的 ALARM 0 命令...")
            self.发送命令(f"{CMD_ALARM_PREFIX}0\n")
            self.last_alarm_level = 0

        # 2. 确保数据视图相关任务已停止 (会关闭 Socket, 绘图窗口等)
        print("步骤 2: 关闭数据视图...")
        self._关闭数据视图()  # 调用这个应该会处理 Socket 和 DataViewer 窗口

        # 3. 停止串口读取线程
        print("步骤 3: 停止串口读取线程...")
        self.串口运行中 = False  # 设置标志让线程退出循环
        if hasattr(self, '串口读取线程') and self.串口读取线程 and self.串口读取线程.is_alive():
            print("  等待串口读取线程结束...")
            self.串口读取线程.join(timeout=THREAD_JOIN_TIMEOUT)  # 等待线程结束
            if self.串口读取线程.is_alive():
                print("  警告: 串口读取线程未能在超时内结束。")
            self.串口读取线程 = None  # 清理引用

        # Socket 线程应该已经在 _关闭数据视图 中停止了

        # 4. 关闭串口连接 (再次确认，以防万一)
        print("步骤 4: 关闭 Arduino 串口连接...")
        if self.arduino串口 and self.arduino串口.is_open:
            try:
                self.arduino串口.close()
                print("  串口已关闭。")
            except Exception as e:
                print(f"  关闭串口时出错: {e}")
        self.arduino串口 = None  # 清理引用

        # 5. 关闭数据库连接
        print("步骤 5: 关闭数据库连接...")
        if self.数据库连接:
            try:
                self.数据库连接.close()
                print("  数据库连接已关闭。")
            except Exception as e:
                print(f"  关闭数据库时出错: {e}")
        self.数据库连接 = None  # 清理引用

        # 6. 销毁主窗口，退出程序
        print("步骤 6: 销毁主窗口...")
        try:
            if self.主窗口 and self.主窗口.winfo_exists():
                self.主窗口.destroy()
        except tk.TclError:
            pass  # 窗口可能已被销毁
        print("应用程序退出。")

    # --- 主程序入口 ---
if __name__ == "__main__":
    print("应用程序启动...")
    主窗口 = tk.Tk()
    应用 = None  # 初始化为 None
    try:
        应用 = ArduinoMonitorApp(主窗口)  # 实例化应用程序类
        # 简单的检查，确保主窗口存在
        if 主窗口 and 主窗口.winfo_exists():
            主窗口.mainloop()  # 进入 Tkinter 事件循环
        else:
            print("应用程序初始化失败，主窗口未创建。")

    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，正在执行关闭处理...")
        if 应用 and hasattr(应用, '_窗口关闭处理'):
            应用._窗口关闭处理()
            print("关闭处理已完成 (来自 Ctrl+C)。")
        else:
            print("应用对象未完全初始化，尝试销毁主窗口...")
            try:
                if 主窗口 and 主窗口.winfo_exists(): 主窗口.destroy()
            except Exception:
                pass

    except Exception as e:
        print(f"主程序发生未捕获错误: {e}")
        traceback.print_exc()
        # 尝试执行清理
        if 应用 and hasattr(应用, '_窗口关闭处理'):
            try:
                应用._窗口关闭处理()
            except Exception as cleanup_e:
                print(f"尝试在错误后清理时发生额外错误: {cleanup_e}")
        else:
            print("应用对象不存在，无法执行标准清理。")
            try:
                if 主窗口 and 主窗口.winfo_exists(): 主窗口.destroy()
            except Exception:
                pass

    print("应用程序已退出。")



