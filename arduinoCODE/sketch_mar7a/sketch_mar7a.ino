// Arduino Radar + DHT/LED Controller - Combined & Modular
// Version 4.3: Buzzer Alarm with LOW level trigger support

#include <Servo.h>
#include <NewPing.h>
#include <DHT.h>

// --- Pin Definitions ---
const int RADAR_SERVO_PIN = 3;
const int RADAR_TRIG_PIN = 4;
const int RADAR_ECHO_PIN = 5;
const int DHT_PIN = 2;
const int LED_PIN = 13;
const int BUZZER_PIN = 8; // 蜂鸣器引脚

// --- Sensor & Communication Configuration ---
// ... (保持不变) ...
const unsigned int RADAR_MAX_DISTANCE_CM = 200;
const uint8_t DHT_SENSOR_TYPE = DHT11;
const unsigned long SERIAL_BAUD_RATE = 115200;
const unsigned long SERIAL_TIMEOUT_MS = 10;
const float RADAR_INVALID_DISTANCE_MARKER = RADAR_MAX_DISTANCE_CM + 1.0;
const int ALARM_OFF = 0;
const int ALARM_SLOW = 1;
const int ALARM_MEDIUM = 2;
const int ALARM_FAST = 3;

// --- Object Instances ---
// ... (保持不变) ...
NewPing radarSonar(RADAR_TRIG_PIN, RADAR_ECHO_PIN, RADAR_MAX_DISTANCE_CM);
Servo radarServo;
DHT dht(DHT_PIN, DHT_SENSOR_TYPE);

// --- Radar Scan Parameters ---
// ... (保持不变) ...
volatile int radar_min_angle = 0;
volatile int radar_max_angle = 180;
volatile int radar_scan_step = 5;
volatile unsigned int radar_scan_delay_ms = 50;

// --- Internal State ---
// ... (其他状态保持不变) ...
int current_servo_pos = 0;
bool radar_scanning_forward = true;
volatile bool is_radar_active = false;
volatile int current_alarm_level = ALARM_OFF;
unsigned long last_beep_time = 0;
const int BEEP_DURATION_MS = 50;
// 对于低电平触发的有源蜂鸣器，通常不需要 PWM 频率
// 如果是无源蜂鸣器需要驱动，则保留频率
// const int BEEP_FREQUENCY_HZ = 1500; // 可能不再需要

// ================== SETUP ==================
void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  initializePins();
  initializeSensorsAndActuators();
  Serial.setTimeout(SERIAL_TIMEOUT_MS);
  Serial.println("INFO: Arduino Ready.");
  Serial.println("Radar Start");
}

// ================== MAIN LOOP ==================
void loop() {
  handleSerialCommands();

  if (is_radar_active) {
    performRadarScanStep();
  } else {
     delay(5);
     if (current_alarm_level != ALARM_OFF) {
         current_alarm_level = ALARM_OFF;
         // <<< 修改：确保停止时为 HIGH >>>
         digitalWrite(BUZZER_PIN, HIGH); // 设为高电平停止蜂鸣器
         // noTone(BUZZER_PIN); // 对于有源蜂鸣器，可能不需要 noTone
     }
  }

  handleAlarmBeep(); // 处理蜂鸣器逻辑

  // delay(1); // 保持或移除
  handleSerialCommands();
}

// ================== INITIALIZATION ==================
void initializePins() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  // <<< 修改：设置蜂鸣器引脚初始状态为 HIGH (不响) >>>
  digitalWrite(BUZZER_PIN, HIGH);
}
// ... (initializeSensorsAndActuators 保持不变) ...
void initializeSensorsAndActuators() {
  dht.begin();
  radarServo.attach(RADAR_SERVO_PIN);
  current_servo_pos = radar_min_angle;
  radarServo.write(current_servo_pos);
  radar_scanning_forward = true;
  delay(500);
}


// ================== RADAR FUNCTIONS ==================
// ... (雷达相关函数保持不变) ...
void performRadarScanStep() {
  int min_angle = radar_min_angle; int max_angle = radar_max_angle;
  int scan_step = radar_scan_step; unsigned int scan_delay = radar_scan_delay_ms;
  int next_pos = calculateNextRadarPosition(min_angle, max_angle, scan_step);
  if (next_pos != current_servo_pos) {
    moveRadarServoTo(next_pos);
    delay(scan_delay);
  } else { delay(1); }
  float distance = measureRadarDistance();
  sendRadarData(current_servo_pos, distance);
}
int calculateNextRadarPosition(int min_angle, int max_angle, int scan_step) {
  int next_pos;
  if (radar_scanning_forward) {
    next_pos = current_servo_pos + scan_step;
    if (next_pos >= max_angle) { next_pos = max_angle; radar_scanning_forward = false; }
  } else {
    next_pos = current_servo_pos - scan_step;
    if (next_pos <= min_angle) { next_pos = min_angle; radar_scanning_forward = true; }
  }
  return next_pos;
}
void moveRadarServoTo(int position) {
  current_servo_pos = position; radarServo.write(current_servo_pos);
}
float measureRadarDistance() {
  unsigned int duration_us = radarSonar.ping(); float dist_cm = radarSonar.convert_cm(duration_us);
  return (dist_cm == 0) ? RADAR_INVALID_DISTANCE_MARKER : dist_cm;
}
void sendRadarData(int angle, float distance) {
  Serial.print(angle); Serial.print(","); Serial.println(distance);
}


// ================== DHT/LED FUNCTIONS ==================
// ... (DHT/LED 函数保持不变) ...
void controlLed(bool turnOn) {
  digitalWrite(LED_PIN, turnOn ? HIGH : LOW);
  if (turnOn) { Serial.println("command=arduino1;light=on;"); }
  else        { Serial.println("command=arduino2;light=off;"); }
}
void readAndSendTemperature() {
  float temperature = dht.readTemperature();
  if (isnan(temperature)) { Serial.println("command=arduino3;error=Failed to read temperature;"); }
  else { Serial.print("command=arduino3;temp="); Serial.print(temperature, 1); Serial.println(";"); }
}
void readAndSendHumidity() {
  float humidity = dht.readHumidity();
  if (isnan(humidity)) { Serial.println("command=arduino4;error=Failed to read humidity;"); }
  else { Serial.print("command=arduino4;humi="); Serial.print(humidity, 1); Serial.println(";"); }
}


// ================== ALARM BEEP FUNCTION ==================
// <<< 修改：适配低电平触发 >>>
void handleAlarmBeep() {
  static bool is_beeping = false; // 跟踪当前是否处于鸣叫状态
  unsigned long current_millis = millis();

  if (current_alarm_level == ALARM_OFF) {
    // 如果当前级别是 OFF，确保蜂鸣器不响 (HIGH)
    if (is_beeping) {
      digitalWrite(BUZZER_PIN, HIGH);
      is_beeping = false;
    }
    return;
  }

  // 如果当前级别不是 OFF，则需要进行周期性鸣叫
  unsigned long interval = 10000; // Default long interval
  switch (current_alarm_level) {
    case ALARM_FAST:   interval = 150; break;
    case ALARM_MEDIUM: interval = 400; break;
    case ALARM_SLOW:   interval = 800; break;
  }

  // 检查是否到达下一个状态切换时间点
  if (current_millis - last_beep_time >= interval) {
      // 如果当前未在鸣叫，则开始鸣叫 (设置为 LOW)
      if (!is_beeping) {
          digitalWrite(BUZZER_PIN, LOW); // 开始鸣叫
          is_beeping = true;
          last_beep_time = current_millis; // 记录鸣叫开始时间
      }
  }

  // 检查鸣叫是否已达到指定持续时间
  if (is_beeping && (current_millis - last_beep_time >= BEEP_DURATION_MS)) {
      digitalWrite(BUZZER_PIN, HIGH); // 停止鸣叫 (设置为 HIGH)
      is_beeping = false;
      // 不需要更新 last_beep_time，下次检查 interval 时会重新计算
      // 为了让 interval 从 beep 结束开始计算，可以更新:
      // last_beep_time = current_millis; // Uncomment this line if interval should start after beep ends
      // 但通常 interval 是指 beep 开始到下一次 beep 开始的时间
  }
}


// ================== SERIAL COMMAND HANDLING ==================
void handleSerialCommands() { /* ... (保持不变) ... */
   while (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n'); command.trim();
    if (command.length() > 0) { processReceivedCommand(command); }
  }
}

void processReceivedCommand(String command) {
  if (command.startsWith("command=arduino")) {
    // ... (处理 arduino1-4，保持不变) ...
    if (command.startsWith("command=arduino1")) { controlLed(true); }
    else if (command.startsWith("command=arduino2")) { controlLed(false); }
    else if (command.startsWith("command=arduino3")) { readAndSendTemperature(); }
    else if (command.startsWith("command=arduino4")) { readAndSendHumidity(); }
    else { Serial.println("ERROR=Unknown arduino command;"); }
  }
  else if (command.equalsIgnoreCase("RADAR_ON")) {
    // ... (处理 RADAR_ON，保持不变) ...
    if (!is_radar_active) { is_radar_active = true; Serial.println("OK RADAR_ON"); }
    else { Serial.println("INFO RADAR_ON (already on)"); }
  }
  else if (command.equalsIgnoreCase("RADAR_OFF")) {
     // ... (处理 RADAR_OFF) ...
     if (is_radar_active) {
        is_radar_active = false;
        current_alarm_level = ALARM_OFF;
        // <<< 修改：确保停止时为 HIGH >>>
        digitalWrite(BUZZER_PIN, HIGH); // 设为高电平停止蜂鸣器
        Serial.println("OK RADAR_OFF");
     } else {
         Serial.println("INFO RADAR_OFF (already off)");
     }
  }
  else if (command.startsWith("ALARM ")) {
    int level = command.substring(6).toInt();
    if (level >= ALARM_OFF && level <= ALARM_FAST) {
      if (level != current_alarm_level) {
        current_alarm_level = level;
        Serial.print("OK ALARM level set to ");
        Serial.println(level);
        if (level == ALARM_OFF) {
           // <<< 修改：确保级别为 0 时设置为 HIGH >>>
           digitalWrite(BUZZER_PIN, HIGH); // 设为高电平停止蜂鸣器
        }
      } else {
        // 可选提示
      }
    } else {
      Serial.println("ERROR Invalid ALARM level");
    }
  }
  else if (command.length() > 1 && isalpha(command.charAt(0)) && (isdigit(command.charAt(1)) || command.charAt(1) == '-')) {
     processRadarParameterCommand(command); // (保持不变)
  }
  else if (command.equalsIgnoreCase("PING?")) { Serial.println("PONG!"); }
  else {
    Serial.print("ERROR=Unknown command format:"); Serial.println(command);
  }
}

void processRadarParameterCommand(String command) { /* ... (保持不变) ... */
    char type = command.charAt(0); String valueStr = command.substring(1); int value = valueStr.toInt();
    bool success = false; int temp_min = radar_min_angle; int temp_max = radar_max_angle;
    switch (toupper(type)) {
      case 'A': if (value >= 0 && value <= 180 && value > temp_min) { radar_max_angle = value; success = true; } break;
      case 'a': if (value >= 0 && value <= 180 && value < temp_max) { radar_min_angle = value; success = true; } break;
      case 'S': if (value > 0 && value <= 30) { radar_scan_step = value; success = true; } break;
      case 'D': if (value >= 10 && value <= 200) { radar_scan_delay_ms = value; success = true; } break;
    }
    if (success) { Serial.print("OK "); } else { Serial.print("ERR "); } Serial.println(command);
}