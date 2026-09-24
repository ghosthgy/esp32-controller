/*
 * ESP32-C3 BLE HID 手机网络ADB无线调试自动开启控制器 (test2.ino)
 * 
 * 基于 BlynkGO/ESP32-BLE-Combo 经典库:
 * https://github.com/BlynkGO/ESP32-BLE-Combo
 * 
 * 说明：
 * 1. 使用 <BleCombo.h> 中的 Keyboard 与 Mouse 对象
 * 2. 兼容 PC 端 Python 控制软件 / EXE 串口通信协议 (115200 波特率)
 * 3. 支持一键自动化开启手机网络 ADB 调试与手动单步调试控制
 * 4. 支持双串口 (Serial + Serial0) 同步输出与监听
 */

#include <BleCombo.h>

// 状态变量
bool lastBleConnected = false;
bool isRunningFlow = false;
unsigned long lastStatusReport = 0;

// 函数声明
void printDual(String msg);
void printDualF(const char *format, ...);
void processSerialCommand(String cmd);
void executeAdbFlow(int preset, String pin);
void wakeUpPhone();
void unlockScreen(String pin);
void sendComboKey(uint8_t modifier, uint8_t key);
void dragMouse(int dx, int dy, int steps, int stepDelay);
void logMsg(String msg);
void reportProgress(int currentStep, int totalSteps, String stepName);
void checkBleState();

// 双串口打印助手 (同时输出到 Serial 和 Serial0/CH340)
void printDual(String msg) {
  Serial.println(msg);
  Serial0.println(msg);
}

void printDualF(const char *format, ...) {
  char buf[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buf, sizeof(buf), format, args);
  va_end(args);
  Serial.println(buf);
  Serial0.println(buf);
}

void setup() {
  // 同时启动两路串口
  Serial.begin(115200);
  Serial0.begin(115200);
  delay(1200);

  printDual("");
  printDual("=================================================");
  printDual("  ESP32-C3 ADB Master (BlynkGO BleCombo Engine)  ");
  printDual("=================================================");

  printDualF("[DEBUG] Chip: %s | Rev: %d | FreeHeap: %u bytes", 
             ESP.getChipModel(), ESP.getChipRevision(), ESP.getFreeHeap());

  // 启动 BlynkGO BleCombo 键鼠引擎
  printDual("[INFO] Starting Keyboard & Mouse BLE stack...");
  Keyboard.begin();
  Mouse.begin();

  printDual("[READY] BleCombo Started! Device Name: ESP32-C3 ADB");
  printDual("[STATUS] BLE:0");
  printDual("=================================================\n");
}

void loop() {
  checkBleState();

  // 监听来自 Serial 的指令
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) processSerialCommand(cmd);
  }

  // 监听来自 Serial0 (CH340) 的指令
  if (Serial0.available() > 0) {
    String cmd = Serial0.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) processSerialCommand(cmd);
  }

  // 定期上报心跳状态（每 3 秒一次）
  if (millis() - lastStatusReport > 3000) {
    lastStatusReport = millis();
    bool isConnected = Keyboard.isConnected();
    printDualF("[STATUS] BLE:%d RUNNING:%d HEAP:%u", 
               isConnected ? 1 : 0, 
               isRunningFlow ? 1 : 0, 
               ESP.getFreeHeap());
  }

  delay(10);
}

// 检查蓝牙连接状态变化
void checkBleState() {
  bool currentConnected = Keyboard.isConnected();
  if (currentConnected != lastBleConnected) {
    lastBleConnected = currentConnected;
    if (currentConnected) {
      printDual("[STATUS] BLE:1");
      logMsg("🎉 蓝牙已成功连接到手机！");
    } else {
      printDual("[STATUS] BLE:0");
      logMsg("⚠️ 蓝牙与手机已断开连接。");
    }
  }
}

// 发送日志给 PC
void logMsg(String msg) {
  printDual("[LOG] " + msg);
}

// 上报执行进度
void reportProgress(int currentStep, int totalSteps, String stepName) {
  printDualF("[PROGRESS] %d/%d %s", currentStep, totalSteps, stepName.c_str());
}

// 组合键发送
void sendComboKey(uint8_t modifier, uint8_t key) {
  Keyboard.press(modifier);
  delay(50);
  Keyboard.press(key);
  delay(80);
  Keyboard.releaseAll();
  delay(100);
}

// 鼠标拖拽模拟滑动手势
void dragMouse(int dx, int dy, int steps, int stepDelay) {
  if (steps <= 0) steps = 20;
  if (stepDelay <= 0) stepDelay = 15;
  Mouse.press(MOUSE_LEFT);
  delay(100);
  int stepX = dx / steps;
  int stepY = dy / steps;
  for (int i = 0; i < steps; i++) {
    Mouse.move(stepX, stepY);
    delay(stepDelay);
  }
  delay(100);
  Mouse.release(MOUSE_LEFT);
  delay(150);
}

// 唤醒手机屏幕
void wakeUpPhone() {
  logMsg("正在唤醒手机屏幕...");
  Keyboard.write(' ');
  delay(150);
  Mouse.click(MOUSE_LEFT);
  delay(300);
}

// 滑动解锁与输入PIN
void unlockScreen(String pin) {
  logMsg("正在滑动解锁屏幕...");
  dragMouse(0, -600, 30, 15);
  delay(500);

  if (pin.length() > 0) {
    logMsg("正在自动输入 PIN 锁屏密码...");
    for (int i = 0; i < pin.length(); i++) {
      Keyboard.write(pin.charAt(i));
      delay(150);
    }
    delay(300);
    Keyboard.write(KEY_RETURN);
    delay(600);
  }
}

// 串口指令解析器
void processSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.equalsIgnoreCase("PING")) {
    printDual("PONG");
    return;
  }
  
  if (cmd.equalsIgnoreCase("STATUS")) {
    printDualF("[STATUS] BLE:%d RUNNING:%d HEAP:%u", 
               Keyboard.isConnected() ? 1 : 0, 
               isRunningFlow ? 1 : 0, 
               ESP.getFreeHeap());
    return;
  }

  if (cmd.equalsIgnoreCase("REBOOT") || cmd.equalsIgnoreCase("RESET")) {
    printDual("[DEBUG] Rebooting ESP32-C3...");
    delay(200);
    ESP.restart();
    return;
  }

  if (cmd.equalsIgnoreCase("STOP")) {
    isRunningFlow = false;
    logMsg("用户已手动中止当前流程。");
    return;
  }

  if (!Keyboard.isConnected()) {
    logMsg("错误: 蓝牙尚未连接到手机！");
    printDual("[ERROR] BLE_NOT_CONNECTED");
    return;
  }

  if (cmd.startsWith("RUN_FLOW")) {
    int firstSpace = cmd.indexOf(' ');
    int secondSpace = cmd.indexOf(' ', firstSpace + 1);
    int preset = 0;
    String pin = "";

    if (firstSpace != -1) {
      if (secondSpace != -1) {
        preset = cmd.substring(firstSpace + 1, secondSpace).toInt();
        pin = cmd.substring(secondSpace + 1);
        pin.trim();
      } else {
        preset = cmd.substring(firstSpace + 1).toInt();
      }
    }
    executeAdbFlow(preset, pin);
    return;
  }

  if (cmd.equalsIgnoreCase("WAKE")) {
    wakeUpPhone();
    return;
  }

  if (cmd.startsWith("UNLOCK")) {
    String pin = "";
    int spaceIndex = cmd.indexOf(' ');
    if (spaceIndex != -1) {
      pin = cmd.substring(spaceIndex + 1);
      pin.trim();
    }
    unlockScreen(pin);
    return;
  }

  if (cmd.startsWith("TYPE ")) {
    String text = cmd.substring(5);
    Keyboard.print(text);
    logMsg("输入文本: " + text);
    return;
  }

  if (cmd.startsWith("KEY ")) {
    String keyName = cmd.substring(4);
    keyName.trim();
    if (keyName.equalsIgnoreCase("ENTER") || keyName.equalsIgnoreCase("RETURN")) {
      Keyboard.write(KEY_RETURN);
    } else if (keyName.equalsIgnoreCase("ESCAPE") || keyName.equalsIgnoreCase("ESC")) {
      Keyboard.write(KEY_ESC);
    } else if (keyName.equalsIgnoreCase("BACKSPACE")) {
      Keyboard.write(KEY_BACKSPACE);
    } else if (keyName.equalsIgnoreCase("TAB")) {
      Keyboard.write(KEY_TAB);
    } else if (keyName.equalsIgnoreCase("SPACE")) {
      Keyboard.write(' ');
    } else if (keyName.equalsIgnoreCase("HOME")) {
      sendComboKey(KEY_LEFT_GUI, KEY_RETURN);
    } else if (keyName.equalsIgnoreCase("BACK")) {
      Keyboard.write(KEY_ESC);
    } else if (keyName.equalsIgnoreCase("UP")) {
      Keyboard.write(KEY_UP_ARROW);
    } else if (keyName.equalsIgnoreCase("DOWN")) {
      Keyboard.write(KEY_DOWN_ARROW);
    } else if (keyName.equalsIgnoreCase("LEFT")) {
      Keyboard.write(KEY_LEFT_ARROW);
    } else if (keyName.equalsIgnoreCase("RIGHT")) {
      Keyboard.write(KEY_RIGHT_ARROW);
    } else if (keyName.equalsIgnoreCase("GUI") || keyName.equalsIgnoreCase("WIN")) {
      Keyboard.write(KEY_LEFT_GUI);
    } else if (keyName.length() == 1) {
      Keyboard.write(keyName.charAt(0));
    }
    logMsg("按下按键: " + keyName);
    return;
  }

  if (cmd.startsWith("KEY_COMB ")) {
    int s1 = cmd.indexOf(' ');
    int s2 = cmd.indexOf(' ', s1 + 1);
    if (s1 != -1 && s2 != -1) {
      String modStr = cmd.substring(s1 + 1, s2);
      String keyStr = cmd.substring(s2 + 1);
      modStr.trim();
      keyStr.trim();
      
      uint8_t mod = 0;
      if (modStr.equalsIgnoreCase("GUI") || modStr.equalsIgnoreCase("WIN")) mod = KEY_LEFT_GUI;
      else if (modStr.equalsIgnoreCase("CTRL")) mod = KEY_LEFT_CTRL;
      else if (modStr.equalsIgnoreCase("ALT")) mod = KEY_LEFT_ALT;
      else if (modStr.equalsIgnoreCase("SHIFT")) mod = KEY_LEFT_SHIFT;

      uint8_t key = 0;
      if (keyStr.equalsIgnoreCase("ENTER")) key = KEY_RETURN;
      else if (keyStr.equalsIgnoreCase("TAB")) key = KEY_TAB;
      else if (keyStr.equalsIgnoreCase("SPACE")) key = ' ';
      else if (keyStr.length() == 1) key = keyStr.charAt(0);

      if (mod != 0 && key != 0) {
        sendComboKey(mod, key);
        logMsg("组合键: " + modStr + " + " + keyStr);
      }
    }
    return;
  }

  if (cmd.startsWith("MOUSE_MOVE ")) {
    int s1 = cmd.indexOf(' ');
    int s2 = cmd.indexOf(' ', s1 + 1);
    if (s1 != -1 && s2 != -1) {
      int dx = cmd.substring(s1 + 1, s2).toInt();
      int dy = cmd.substring(s2 + 1).toInt();
      Mouse.move(dx, dy);
    }
    return;
  }

  if (cmd.startsWith("MOUSE_CLICK")) {
    int s1 = cmd.indexOf(' ');
    String btn = "LEFT";
    if (s1 != -1) btn = cmd.substring(s1 + 1);
    btn.trim();
    if (btn.equalsIgnoreCase("RIGHT")) {
      Mouse.click(MOUSE_RIGHT);
    } else {
      Mouse.click(MOUSE_LEFT);
    }
    logMsg("鼠标点击: " + btn);
    return;
  }

  if (cmd.startsWith("MOUSE_DRAG ")) {
    int args[4] = {0, 0, 20, 10};
    int currentPos = cmd.indexOf(' ') + 1;
    for (int i = 0; i < 4 && currentPos < cmd.length(); i++) {
      int nextSpace = cmd.indexOf(' ', currentPos);
      if (nextSpace == -1) nextSpace = cmd.length();
      args[i] = cmd.substring(currentPos, nextSpace).toInt();
      currentPos = nextSpace + 1;
    }
    dragMouse(args[0], args[1], args[2], args[3]);
    logMsg("鼠标拖动完成");
    return;
  }

  if (cmd.startsWith("DELAY ")) {
    int ms = cmd.substring(6).toInt();
    if (ms > 0 && ms <= 10000) {
      delay(ms);
    }
    return;
  }

  logMsg("未知指令: " + cmd);
}

// 核心自动化流程：一键开启网络ADB无线调试
void executeAdbFlow(int preset, String pin) {
  if (isRunningFlow) {
    logMsg("流程已在运行中！");
    return;
  }
  isRunningFlow = true;
  int totalSteps = 6;

  logMsg("开始执行一键开启无线网络 ADB 调试流程 (系统预设: " + String(preset) + ")...");

  // 第 1 步：唤醒屏幕
  reportProgress(1, totalSteps, "唤醒手机屏幕");
  wakeUpPhone();
  delay(500);
  if (!isRunningFlow) return;

  // 第 2 步：滑动解锁 (及输入PIN)
  reportProgress(2, totalSteps, "滑动解锁屏幕");
  unlockScreen(pin);
  delay(800);
  if (!isRunningFlow) return;

  // 第 3 步：快速唤起设置或系统搜索
  reportProgress(3, totalSteps, "打开系统设置");
  
  if (preset == 0) {
    Keyboard.write(KEY_LEFT_GUI);
    delay(400);
    Keyboard.print("settings");
    delay(400);
    Keyboard.write(KEY_RETURN);
  } else if (preset == 1) { // 小米 MIUI / HyperOS
    Keyboard.write(KEY_LEFT_GUI);
    delay(400);
    Keyboard.print("settings");
    delay(400);
    Keyboard.write(KEY_RETURN);
  } else if (preset == 2) { // 华为 HarmonyOS
    sendComboKey(KEY_LEFT_GUI, 'n');
    delay(500);
    Keyboard.write(KEY_LEFT_GUI);
    delay(400);
    Keyboard.print("settings");
    delay(400);
    Keyboard.write(KEY_RETURN);
  } else {
    Keyboard.write(KEY_LEFT_GUI);
    delay(400);
    Keyboard.print("settings");
    delay(400);
    Keyboard.write(KEY_RETURN);
  }
  delay(1200);
  if (!isRunningFlow) return;

  // 第 4 步：在设置中搜索“无线调试”
  reportProgress(4, totalSteps, "搜索无线调试选项");
  sendComboKey(KEY_LEFT_CTRL, 'f');
  delay(400);
  Keyboard.print("wuxiangtiaoshi");
  delay(300);
  Keyboard.write(KEY_BACKSPACE);
  delay(100);
  sendComboKey(KEY_LEFT_CTRL, 'a');
  delay(100);
  Keyboard.print("wireless");
  delay(500);
  Keyboard.write(KEY_RETURN);
  delay(800);
  if (!isRunningFlow) return;

  // 第 5 步：进入无线调试页面并触发开关
  reportProgress(5, totalSteps, "进入并开启无线调试开关");
  Keyboard.write(KEY_DOWN_ARROW);
  delay(200);
  Keyboard.write(KEY_RETURN);
  delay(800);

  Keyboard.write(KEY_RETURN);
  delay(200);
  Keyboard.write(' ');
  delay(500);
  if (!isRunningFlow) return;

  // 第 6 步：确认“是否在此网络上允许无线调试”弹窗
  reportProgress(6, totalSteps, "确认网络调试授权弹窗");
  Keyboard.write(KEY_RIGHT_ARROW);
  delay(200);
  Keyboard.write(KEY_TAB);
  delay(200);
  Keyboard.write(KEY_RETURN);
  delay(200);
  Keyboard.write(' ');

  delay(600);
  isRunningFlow = false;
  reportProgress(6, totalSteps, "完成！无线网络ADB已成功触发开启");
  logMsg("SUCCESS: 无线网络ADB开启流程执行完毕！");
  printDual("[SUCCESS] ADB_ENABLED");
}
