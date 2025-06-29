# server_dht_radar.py (已修正数据处理和插入逻辑)
import threading
import socket
import datetime
import sqlite3
import logging
import signal
import sys
import json
import math
import time

# --- 配置 ---
HOST = ""  # 你本地作为服务器的设备的公网IP
PORT = 8888
DB_NAME = 'dht_radar_storage.db'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(threadName)s - %(message)s'
# -------------

# --- 日志设置 ---
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT) # 可以改为 logging.DEBUG 获取更详细信息
# -------------

# --- 数据库初始化 ---
def init_db():
    """初始化数据库，创建 温湿度表 和 雷达表"""
    try:
        with sqlite3.connect(DB_NAME, timeout=10.0) as conn: # 增加超时
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS environment_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    sensor_type TEXT NOT NULL CHECK(sensor_type IN ('temp', 'humi')),
                    value REAL NOT NULL,
                    unit TEXT,
                    timestamp DATETIME NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS radar_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    angle INTEGER NOT NULL,
                    distance REAL, /* 允许距离为 NULL (如果无效) */
                    timestamp DATETIME NOT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_env_dev_time ON environment_data (device_id, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_radar_dev_time ON radar_data (device_id, timestamp)')
            logging.info(f"Database '{DB_NAME}' initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Database initialization failed: {e}")
        sys.exit(1)
    except Exception as e:
         logging.error(f"Unexpected error during DB init: {e}")
         sys.exit(1)

# --- 数据库访问同步 ---
db_semaphore = threading.Semaphore(1)
# ---------------------

# --- 数据库操作封装 ---
def db_execute(sql, params=()): # 移除了 fetch_one, fetch_all，因为这里只做插入
    """执行数据库插入操作，处理连接、游标和信号量。成功返回 True，失败返回 False。"""
    conn = None
    acquired = False
    success = False
    try:
        db_semaphore.acquire()
        acquired = True
        # detect_types 用于 SQLite 正确解析 DATETIME 等类型
        with sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            # 对于 INSERT，如果执行到这里没有异常，WITH 语句会自动 commit
            logging.debug(f"DB execute OK (rows affected: {cursor.rowcount}): {sql} / {params}")
            success = True # 假设执行成功
    except sqlite3.IntegrityError as ie: # 例如，如果未来添加了唯一约束
        logging.error(f"DB IntegrityError executing '{sql}' / {params}: {ie}")
    except sqlite3.OperationalError as oe: # 例如，数据库锁定或文件问题
        logging.error(f"DB OperationalError executing '{sql}' / {params}: {oe}")
    except sqlite3.Error as e:
        logging.error(f"DB error executing '{sql}' / {params}: {e}")
    except Exception as e:
         logging.error(f"Unexpected DB error executing '{sql}' / {params}: {e}")
    finally:
        if acquired:
            db_semaphore.release()
    return success

# --- 消息解析 ---
def parse_message(data_str):
    """尝试将接收到的字符串解析为 JSON。"""
    data_str = data_str.strip()
    if not data_str:
        return None
    try:
        data = json.loads(data_str)
        # 基本验证：必须是字典
        if isinstance(data, dict):
             logging.debug(f"Parsed JSON: {data}")
             return data
        else:
             logging.warning(f"Parsed JSON but not a dictionary: {data_str}")
             return None
    except json.JSONDecodeError:
        logging.warning(f"Received non-JSON message: {data_str}")
        return None
    except Exception as e:
         logging.error(f"Error during JSON parsing: {e} for data: {data_str}")
         return None

# --- 数据处理逻辑 (重写部分) ---
def handle_client_data(parsed_json_root, client_socket, client_address):
    """
    根据解析后的 JSON 根对象 (期望包含 deviceId, timestamp, payload)
    调用不同的处理函数。
    """
    if not parsed_json_root:
        logging.warning(f"Invalid or unparseable root JSON from {client_address}. Ignored.")
        return

    # 1. 从根 JSON 中提取元数据
    device_id = parsed_json_root.get('deviceId')
    timestamp_str_iso = parsed_json_root.get('timestamp') # 期望是 ISO 格式
    payload = parsed_json_root.get('payload')

    # 验证元数据是否存在
    if not device_id:
        logging.error(f"Missing 'deviceId' in root JSON from {client_address}: {parsed_json_root}")
        # 可以选择回复错误给客户端
        # try: client_socket.send(b"Error: Missing 'deviceId'.") except socket.error: pass
        return
    if not timestamp_str_iso:
        logging.error(f"Missing 'timestamp' in root JSON from {device_id} ({client_address}): {parsed_json_root}")
        # try: client_socket.send(b"Error: Missing 'timestamp'.") except socket.error: pass
        return
    if not isinstance(payload, dict):
        logging.error(f"Missing or invalid 'payload' (must be a dictionary) from {device_id} ({client_address}): {parsed_json_root}")
        # try: client_socket.send(b"Error: Invalid 'payload'.") except socket.error: pass
        return

    # 2. 从 payload 中提取数据类型
    data_type = payload.get('type')
    if not data_type:
        logging.error(f"Missing 'type' in payload from {device_id} ({client_address}): {payload}")
        # try: client_socket.send(b"Error: Missing 'type' in payload.") except socket.error: pass
        return

    logging.info(f"Processing '{data_type}' payload from {device_id} ({client_address})")

    # 3. 解析时间戳 (一次性在这里解析，传递 datetime 对象给后续函数)
    try:
        # ISO 8601 格式通常可以直接用 fromisoformat (Python 3.7+)
        # 或者更通用的方式处理可能存在的 'T' 和毫秒部分
        timestamp_dt = datetime.datetime.fromisoformat(timestamp_str_iso.replace("Z", "+00:00")) # 处理 'Z'
    except ValueError:
        try:
            # 备用解析，只取到秒，忽略毫秒和 'T'
            timestamp_dt = datetime.datetime.strptime(timestamp_str_iso[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        except ValueError as ts_err:
            logging.error(f"Invalid timestamp format '{timestamp_str_iso}' from {device_id}: {ts_err}")
            # try: client_socket.send(b"Error: Invalid timestamp format.") except socket.error: pass
            return

    # 4. 分发到对应的处理函数
    if data_type == 'temp' or data_type == 'humi':
        handle_environment_data(payload, device_id, timestamp_dt, client_socket)
    elif data_type == 'radar':
        handle_radar_data(payload, device_id, timestamp_dt, client_socket)
    elif data_type == 'heartbeat': # 假设客户端也可能发送心跳
         logging.info(f"Received heartbeat from {device_id}.")
         # try: client_socket.send(b"PONG_HEARTBEAT") except socket.error: pass
    else:
        logging.warning(f"Unknown data type '{data_type}' in payload from {device_id}.")
        try: client_socket.send(f"Error: Unknown payload type '{data_type}'".encode('utf-8'))
        except socket.error: pass

def handle_environment_data(payload_data, device_id, timestamp_dt, client_socket):
    """处理来自 payload 的温湿度数据并存入数据库"""
    sensor_type = payload_data.get('type') # 应该已经是 'temp' 或 'humi'
    value_str = payload_data.get('value')
    unit = payload_data.get('unit')
    response_msg = f"Error:Failed_process_{sensor_type}"

    if value_str is None:
        logging.error(f"Missing 'value' for {sensor_type} from {device_id}: {payload_data}")
        response_msg = f"Error:Missing_value_for_{sensor_type}"
    else:
        try:
            value_float = float(value_str)

            # 数据验证
            if sensor_type == 'temp' and not (-50 <= value_float <= 100): # 合理范围
                raise ValueError(f"Temperature value {value_float} out of reasonable range (-50 to 100)")
            if sensor_type == 'humi' and not (0 <= value_float <= 100):
                raise ValueError(f"Humidity value {value_float} out of range (0-100)")
            if math.isnan(value_float):
                raise ValueError(f"{sensor_type} value is NaN")

            # 插入数据库
            if db_execute(
                'INSERT INTO environment_data (device_id, sensor_type, value, unit, timestamp) VALUES (?, ?, ?, ?, ?)',
                (device_id, sensor_type, value_float, unit, timestamp_dt)
            ):
                logging.info(f"DB INSERT OK: {sensor_type} from {device_id}: {value_float}{unit or ''} @ {timestamp_dt}")
                response_msg = f"OK:{sensor_type}_recorded"
            else:
                logging.error(f"DB INSERT FAILED for {sensor_type} from {device_id}.")
                response_msg = f"Error:DB_insert_{sensor_type}_failed"

        except ValueError as ve: # 包括 float转换失败 和 自定义范围错误
             logging.error(f"Invalid value for {sensor_type} from {device_id}: '{value_str}' ({ve})")
             response_msg = f"Error:Invalid_value_for_{sensor_type}"
        except Exception as e:
             logging.exception(f"Unexpected error handling env data from {device_id}: {e}")
             response_msg = "Error:Server_processing_env_data"

    # 发送响应
    try:
        client_socket.sendall((response_msg + '\n').encode('utf-8')) # 添加换行符
    except socket.error:
        logging.warning(f"Failed to send response to {device_id} for env data (socket error).")

def handle_radar_data(payload_data, device_id, timestamp_dt, client_socket):
    """处理来自 payload 的雷达数据并存入数据库"""
    angle_str = payload_data.get('angle')
    distance_str = payload_data.get('distance') # 客户端可能发送 None for distance
    response_msg = "Error:Failed_process_radar"

    if angle_str is None: # angle 必须有
        logging.error(f"Missing 'angle' for radar from {device_id}: {payload_data}")
        response_msg = "Error:Missing_radar_angle"
    else:
        try:
            angle_int = int(float(angle_str)) # 先转 float 再转 int，处理 "90.0" 这样的输入

            # distance 可能为 null/None，或者是一个数字
            distance_val = None
            if distance_str is not None:
                try:
                    distance_val = float(distance_str)
                    if math.isnan(distance_val): # 处理 NaN
                        distance_val = None
                except (ValueError, TypeError):
                    logging.warning(f"Invalid distance value '{distance_str}' for radar from {device_id}, treating as None.")
                    distance_val = None # 无效距离也设为 None

            # 数据验证 (角度必须有效，距离如果不是 None 则必须在范围内)
            # 客户端发送的雷达距离 `null` 会被 json.loads 解析为 Python `None`
            # 客户端发送的雷达无效标记 (如 201.0) 也应该在这里处理或由客户端发送为 None
            MAX_RADAR_DB_DISTANCE = 200.0 # 与客户端雷达图一致
            MIN_RADAR_DB_DISTANCE = 0.1   # 假设一个最小有效距离

            if not (0 <= angle_int <= 180):
                raise ValueError(f"Radar angle {angle_int} out of range (0-180)")

            # 只有当 distance_val 不是 None 时才检查其范围
            if distance_val is not None and not (MIN_RADAR_DB_DISTANCE <= distance_val <= MAX_RADAR_DB_DISTANCE):
                logging.debug(f"Radar distance {distance_val} from {device_id} out of range, storing as NULL.")
                distance_val = None # 超出范围也存为 NULL

            # 插入数据库 (distance_val 可能为 None，数据库字段 radar_data.distance 允许 NULL)
            if db_execute(
                'INSERT INTO radar_data (device_id, angle, distance, timestamp) VALUES (?, ?, ?, ?)',
                (device_id, angle_int, distance_val, timestamp_dt)
            ):
                logging.info(f"DB INSERT OK: radar from {device_id}: A={angle_int}, D={distance_val if distance_val is not None else 'NULL'} @ {timestamp_dt}")
                response_msg = "OK:radar_recorded"
            else:
                logging.error(f"DB INSERT FAILED for radar from {device_id}.")
                response_msg = "Error:DB_insert_radar_failed"

        except ValueError as ve:
             logging.error(f"Invalid angle/distance format for radar from {device_id}: {payload_data} ({ve})")
             response_msg = f"Error:Invalid_radar_format"
        except Exception as e:
             logging.exception(f"Unexpected error handling radar data from {device_id}: {e}")
             response_msg = "Error:Server_processing_radar_data"

    # 发送响应
    try:
        client_socket.sendall((response_msg + '\n').encode('utf-8'))
    except socket.error:
        logging.warning(f"Failed to send response to {device_id} for radar data (socket error).")


# --- 客户端处理线程 ---
def client_handler(client_socket, client_address):
    """处理单个客户端连接，读取数据并分发处理"""
    thread_name = threading.current_thread().name
    logging.info(f"Connection established from {client_address} on {thread_name}")
    buffer = ""
    try:
        client_socket.settimeout(120.0) # 增加超时时间
        while True:
            chunk = client_socket.recv(2048) # 稍微增大接收缓冲区
            if not chunk:
                logging.info(f"Client {client_address} disconnected gracefully.")
                break

            buffer += chunk.decode('utf-8', errors='replace') # 使用 'replace' 处理解码错误

            while '\n' in buffer:
                message, buffer = buffer.split('\n', 1)
                message = message.strip()
                if message:
                    logging.info(f"RAW RX from {client_address}: {message}")
                    parsed_root_json = parse_message(message)
                    handle_client_data(parsed_root_json, client_socket, client_address)

            if len(buffer) > 16384: # 增加缓冲区溢出限制
                 logging.error(f"Buffer overflow from {client_address}. Closing connection.")
                 try: client_socket.sendall(b"Error: Message too long or invalid format.\n")
                 except socket.error: pass
                 break
    except socket.timeout:
         logging.warning(f"Socket timeout for {client_address}.")
    except (socket.error, ConnectionResetError, BrokenPipeError) as e:
        logging.error(f"Socket error with {client_address}: {e}")
    except UnicodeDecodeError as ude:
        logging.error(f"Unicode decode error from {client_address}: {ude}. Ensure client uses UTF-8.")
        try: client_socket.sendall(b"Error: Use UTF-8 encoding.\n")
        except socket.error: pass
    except Exception as e:
        logging.exception(f"Unexpected error in client_handler for {client_address}: {e}")
        try: client_socket.sendall(b"Error: Internal server error.\n")
        except socket.error: pass
    finally:
        logging.info(f"Closing connection from {client_address}")
        try:
            client_socket.shutdown(socket.SHUT_RDWR) # 尝试优雅关闭
        except socket.error:
            pass # 可能已经关闭
        client_socket.close()

# --- 服务器主逻辑 ---
server_socket = None

def shutdown_server(signum, frame):
    """优雅地关闭服务器"""
    logging.info(f"Received signal {signum}. Shutting down server...")
    global server_socket
    if server_socket:
        try:
            # Set a flag or use other mechanism to stop worker threads if they are long-running
            # For simple request-response, closing the server socket is often enough.
            server_socket.close()
        except Exception as e:
            logging.error(f"Error closing server socket: {e}")
    # Give threads some time to finish, then exit
    # This part can be more sophisticated depending on thread tasks
    logging.info("Waiting for active threads to complete (max 5s)...")
    # A more robust shutdown might involve joining threads, but daemon threads will exit with main
    time.sleep(1) # Brief pause
    logging.info("Server shut down.")
    sys.exit(0)

def main():
    global server_socket
    init_db()

    signal.signal(signal.SIGINT, shutdown_server)
    signal.signal(signal.SIGTERM, shutdown_server)

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(15) # 增加监听队列
        logging.info(f"Server listening on {HOST}:{PORT}...")

        active_threads = []
        while True:
            try:
                new_socket, client_addr = server_socket.accept()
                client_thread = threading.Thread(
                    target=client_handler,
                    args=(new_socket, client_addr),
                    daemon=True # Daemon threads will exit when main thread exits
                )
                client_thread.start()
                # (Optional) Keep track of threads if non-daemon and need explicit joining on shutdown
                # active_threads.append(client_thread)
                # active_threads = [t for t in active_threads if t.is_alive()] # Clean up list
            except OSError as e:
                # This error (e.g., [Errno 9] Bad file descriptor) occurs when server_socket is closed by shutdown_server
                logging.info(f"Server socket closed ({e}). Exiting accept loop.")
                break
            except Exception as e:
                logging.exception(f"Error accepting new connection: {e}")
                time.sleep(0.1) # Prevent busy loop on persistent accept errors

    except Exception as e:
        logging.exception(f"Critical error in server main loop: {e}")
    finally:
        logging.info("Server main process finishing.")
        if server_socket:
             try:
                  server_socket.close()
             except Exception: pass # Ignore errors on final close

if __name__ == "__main__":
    main()
