# arduino_comm.py
# 处理与 Arduino 雷达设备的串口通信。

import glob  # 用于查找串口 (Linux/Mac)
import sys  # 用于平台判断
import time  # 用于延时

import serial  # 导入 pyserial 库

from . import config


class ArduinoConnection:
    """管理与 Arduino 的串口连接和通信。"""
    def __init__(self, baud_rate=config.BAUD_RATE, timeout=config.SERIAL_TIMEOUT_S):
        """初始化 Arduino 连接对象。"""
        self.ser = None                 # serial 对象实例，初始为 None
        self.baud_rate = baud_rate      # 波特率
        self.timeout = timeout          # 读取超时
        self.port = None                # 连接的端口名
        self.is_started = False         # 是否已接收到 Arduino 的启动信号
        self.last_command_sent = {}     # 记录上次发送的指令，避免重复发送

    def find_port(self):
        """搜索可能连接着 Arduino 的可用串口。"""
        # 根据操作系统类型确定查找串口的方式
        if sys.platform.startswith('win'): # Windows
            ports = ['COM{0:1.0f}'.format(ii) for ii in range(1,256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'): # Linux 或 Cygwin
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'): # macOS
            ports = glob.glob('/dev/tty.*')
        else:
            # 如果是不支持的系统，则抛出环境错误
            raise EnvironmentError('当前操作系统不支持 pyserial 自动搜索端口。')

        arduinos = []
        for p in ports:
            # 尝试排除常见的非 Arduino 串口，如蓝牙
            if 'Bluetooth' in p or 'Wireless' in p: continue
            try:
                # 尝试打开和关闭串口以检查其有效性
                s = serial.Serial(p)
                s.close()
                arduinos.append(p) # 如果成功，则添加到列表中
            except (OSError, serial.SerialException):
                # 如果打开失败，则忽略这个端口
                pass
        return arduinos # 返回找到的可能端口列表

    def connect(self, selected_port=None):
        """建立到 Arduino 的串口连接。"""
        # 如果已经连接，则直接返回 True
        if self.ser and self.ser.is_open:
            print("已经连接。")
            return True

        # 如果用户指定了端口，则使用指定的端口
        if selected_port:
            self.port = selected_port
        else:
            # 否则，自动搜索端口
            available_ports = self.find_port()
            if not available_ports:
                print("错误：未找到可用的 Arduino 端口。")
                return False
            self.port = available_ports[0] # 默认使用找到的第一个端口
            print(f"找到可用端口: {available_ports}")

        print(f"尝试连接端口: {self.port}")
        try:
            # 创建 Serial 对象并打开端口
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            # 清空输入和输出缓冲区，防止旧数据干扰
            self.ser.flushInput()
            self.ser.flushOutput()
            print(f"成功连接到 {self.port}")
            # 短暂等待，让 Arduino 可能完成重置并发送初始数据
            time.sleep(2)
            return True
        except serial.SerialException as e:
            # 捕获串口特定错误
            print(f"错误：无法打开串口 {self.port}: {e}")
            self.ser = None # 连接失败，重置 serial 对象
            return False
        except Exception as e:
            # 捕获其他可能的连接错误
            print(f"连接串口时发生错误: {e}")
            self.ser = None
            return False

    def disconnect(self):
        """关闭串口连接。"""
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print("串口已关闭。")
            except Exception as e:
                print(f"关闭串口时发生错误: {e}")
        self.ser = None         # 重置 serial 对象
        self.is_started = False # 重置启动状态
        self.last_command_sent.clear() # 清空指令发送历史

    def is_connected(self):
        """检查串口连接是否处于活动状态。"""
        return self.ser is not None and self.ser.is_open

    def read_data(self):
        """从串口读取可用行，并处理启动信号和响应信息。"""
        if not self.is_connected():
            return None, None # 如果未连接，返回 None

        lines_data = []       # 用于存储读取到的有效数据行 ("角度,距离")
        status_message = None # 用于存储特殊状态信息 (如 "STARTED", "DISCONNECTED")

        try:
            # 检查输入缓冲区是否有数据
            if self.ser.in_waiting > 0:
                # 读取所有可用字节，并尝试解码为 UTF-8 字符串
                all_incoming = self.ser.read_all().decode('utf-8', errors='ignore')
                # 按换行符分割成多行
                lines = all_incoming.strip().split('\n')

                for line in lines:
                    line = line.strip() # 去除单行首尾空白
                    if not line: continue # 跳过空行

                    # 如果尚未收到启动信号
                    if not self.is_started:
                        if line == config.START_SIGNAL: # 检查是否是启动信号
                            self.is_started = True
                            status_message = "STARTED" # 设置状态为已启动
                            print("接收到雷达启动信号。")
                            self.last_command_sent.clear() # 清空指令历史，允许发送初始参数
                        else:
                            # 在启动前忽略其他数据
                            # print(f"等待启动信号，收到: {line}") # 调试信息
                            pass
                    else:
                        # 启动后，检查是否是 Arduino 的响应信息
                        if line.startswith("OK ") or line.startswith("ERR "):
                             print(f"Arduino 响应: {line}") # 打印响应信息
                             # 可以考虑将此响应信息也作为状态返回
                        elif ',' in line: # 如果包含逗号，假定为数据行
                            lines_data.append(line)
                        # else: # 启动后忽略无法识别的行
                        #    print(f"忽略无法识别的行: {line}") # 调试信息

        except serial.SerialException as e:
            # 如果发生串口错误（例如设备断开）
            print(f"串口读取错误: {e}")
            self.disconnect() # 断开连接
            return "DISCONNECTED", None # 返回断开状态
        except Exception as e:
            # 捕获其他读取错误
            print(f"从串口读取时发生错误: {e}")
            # 根据错误类型决定是否需要断开连接
            return "ERROR", None # 返回错误状态

        # 返回状态信息和数据行列表
        return status_message, lines_data

    def send_command(self, cmd_prefix, value):
        """向 Arduino 发送指令，避免发送冗余指令。"""
        if not self.is_connected():
            print("错误：无法发送指令，串口未连接。")
            return False

        command_key = cmd_prefix # 使用指令前缀 (如 'A', 'a') 作为键
        value = int(value)       # 确保值为整数，便于比较和发送

        # 检查是否与上次发送的该指令的值相同
        if command_key in self.last_command_sent and self.last_command_sent[command_key] == value:
            return True # 值未改变，无需发送

        # 格式化指令字符串 (例如 "A120\n")
        command = f"{cmd_prefix}{value}\n"
        try:
            # 将指令编码为 UTF-8 字节并发送
            self.ser.write(command.encode('utf-8'))
            print(f"已发送指令: {command.strip()}")
            self.last_command_sent[command_key] = value # 更新发送历史
            return True
        except Exception as e:
            print(f"发送指令 {command.strip()} 时发生错误: {e}")
            # 考虑此错误是否意味着连接断开
            return False