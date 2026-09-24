/*
 * ESP32-C3 BLE HID 手机网络ADB无线调试自动开启控制器
 * 
 * 双串口兼容 (Native USB CDC + CH340 UART0) + 深度诊断
 */

#include <ESP32BLECombo.h>

// ================= 标准键盘与鼠标按键常量定义 =================
#ifndef KEY_LEFT_CTRL
#define KEY_LEFT_CTRL     0x80
#define KEY_LEFT_SHIFT    0x81
#define KEY_LEFT_ALT      0x82
#define KEY_LEFT_GUI      0x83
#define KEY_RIGHT_CTRL    0x84
#define KEY_RIGHT_SHIFT   0x85
#define KEY_RIGHT_ALT     0x86
#define KEY_RIGHT_GUI     0x87

#define KEY_RETURN        0xB0  // 136 + 0x28
#define KEY_ESC           0xB1  // 136 + 0x29
#define KEY_BACKSPACE     0xB2  // 136 + 0x2A
#define KEY_TAB           0xB3  // 136 + 0x2B
#define KEY_CAPS_LOCK     0xC1  // 136 + 0x39
#define KEY_RIGHT_ARROW   0xD7  // 136 + 0x4F
#define KEY_LEFT_ARROW    0xD8  // 136 + 0x50
#define KEY_DOWN_ARROW    0xD9  // 136 + 0x51
#define KEY_UP_ARROW      0xDA  // 136 + 0x52
#define KEY_HOME          0xD2  // 136 + 0x4A
#define KEY_END           0xD5  // 136 + 0x4D
#define KEY_PAGE_UP       0xD3  // 136 + 0x4B
#define KEY_PAGE_DOWN     0xD4  // 136 + 0x4E
#endif

#ifndef MOUSE_LEFT
#define MOUSE_LEFT        ESP32BLECombo::MOUSE_LEFT
#define MOUSE_RIGHT       ESP32BLECombo::MOUSE_RIGHT
#define MOUSE_MIDDLE      ESP32BLECombo::MOUSE_MIDDLE
#endif

ESP32BLECombo ble;

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
void smoothMouseMove(int totalDx, int totalDy, int steps, int stepDelay);
void dragMouse(int dx, int dy, int steps, int stepDelay);
void logMsg(String msg);
void reportProgress(int currentStep, int totalSteps, String stepName);
void checkBleState();
void printBleDiagnostics();

// 双串口打印助手 (同时输出到 Serial 和 Serial0)
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
  // 同时初始化 UART0 (CH340) 与 Native USB CDC
  Serial.begin(115200);
  Serial0.begin(115200);
  delay(1500); // 确保串口平稳建立

  printDual("");
  printDual("=================================================");
  printDual("  ESP32-C3 Wireless ADB Controller - Boot OK!    ");
  printDual("=================================================");

  printDualF("[DEBUG] Chip: %s | Rev: %d | SDK: %s", 
             ESP.getChipModel(), ESP.getChipRevision(), ESP.getSdkVersion());
  printDualF("[DEBUG] Free Heap Before BLE: %u bytes", ESP.getFreeHeap());

  // 配置 BLE 蓝牙参数
  ESP32BLEComboConfig cfg;
  cfg.mode = ESP32BLEComboMode::KEYBOARD_MOUSE;
  cfg.deviceName = "ESP32-C3 ADB";  // 保持简短，防止广播包超 31 字节
  cfg.manufacturer = "Espressif";
  cfg.batteryLevel = 100;
  cfg.appearance = ESP32BLEComboAppearance::AUTO;
  cfg.enableSecurity = true;
  cfg.keyPressDelayMs = 20;
  cfg.keyReleaseDelayMs = 20;
  cfg.keyIntervalDelayMs = 10;

  printDual("[DEBUG] Starting ble.begin(cfg)...");
  bool ok = ble.begin(cfg);
  
  if (ok) {
    printDual("[READY] ble.begin() SUCCESS!");
  } else {
    printDual("[ERROR] ble.begin() FAILED!");
  }

  printDualF("[DEBUG] Free Heap After BLE: %u bytes", ESP.getFreeHeap());

  // 输出蓝牙诊断数据
  printBleDiagnostics();

  printDual("[STATUS] BLE:0");
  printDual("=================================================\n");
}

void loop() {
  checkBleState();

  // 处理来自 Serial 的指令
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) processSerialCommand(cmd);
  }

  // 处理来自 Serial0 (CH340) 的指令
  if (Serial0.available() > 0) {
    String cmd = Serial0.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) processSerialCommand(cmd);
  }

  // 定期上报心跳状态（每 3 秒一次）
  if (millis() - lastStatusReport > 3000) {
    lastStatusReport = millis();
    bool isConnected = ble.isConnected();
    bool isAdv = false;
    
    // 检查底层 NimBLE 广播状态
    if (NimBLEDevice::getServer() != nullptr && NimBLEDevice::getAdvertising() != nullptr) {
      isAdv = NimBLEDevice::getAdvertising()->isAdvertising();
      // 如果未连接且未在广播，主动恢复广播
      if (!isConnected && !isAdv) {
        printDual("[DEBUG] Re-enabling BLE Advertising...");
        NimBLEDevice::startAdvertising();
        isAdv = true;
      }
    }

    printDualF("[STATUS] BLE:%d RUNNING:%d ADV:%d HEAP:%u", 
               isConnected ? 1 : 0, 
               isRunningFlow ? 1 : 0, 
               isAdv ? 1 : 0, 
               ESP.getFreeHeap());
  }

  delay(10);
}

// 打印蓝牙底层诊断信息
void printBleDiagnostics() {
  printDual("------------- [BLE DIAGNOSTICS] -------------");
  printDual("  Device Name:   ESP32-C3 ADB");
  printDualF("  BLE MAC Addr:  %s", NimBLEDevice::getAddress().toString().c_str());
  
  if (NimBLEDevice::getAdvertising() != nullptr) {
    bool isAdv = NimBLEDevice::getAdvertising()->isAdvertising();
    printDualF("  Advertising:   %s", isAdv ? "ACTIVE (Broadcasting...)" : "INACTIVE");
  } else {
    printDual("  Advertising:   NULL (Not initialized!)");
  }
  
  printDualF("  BLE Connected: %s", ble.isConnected() ? "YES" : "NO (Waiting for phone...)");
  printDual("---------------------------------------------");
}

// 检查蓝牙连接状态变化
void checkBleState() {
  bool currentConnected = ble.isConnected();
  if (currentConnected != lastBleConnected) {
    lastBleConnected = currentConnected;
    if (currentConnected) {
      printDual("[STATUS] BLE:1");
      logMsg("🎉 BLE Connected to Phone!");
    } else {
      printDual("[STATUS] BLE:0");
      logMsg("⚠️ BLE Disconnected from Phone.");
      NimBLEDevice::startAdvertising();
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

// 串口指令解析器
void processSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.equalsIgnoreCase("PING")) {
    printDual("PONG");
    return;
  }
  
  if (cmd.equalsIgnoreCase("STATUS") || cmd.equalsIgnoreCase("DIAG")) {
    printBleDiagnostics();
    printDualF("[STATUS] BLE:%d RUNNING:%d HEAP:%u", ble.isConnected() ? 1 : 0, isRunningFlow ? 1 : 0, ESP.getFreeHeap());
    return;
  }

  if (cmd.equalsIgnoreCase("ADV") || cmd.equalsIgnoreCase("START_ADV")) {
    printDual("[DEBUG] Manually restarting BLE advertising...");
    NimBLEDevice::startAdvertising();
    printBleDiagnostics();
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
    logMsg("Flow execution stopped by user.");
    return;
  }

  if (!ble.isConnected()) {
    logMsg("ERROR: BLE is not connected to phone!");
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
    ble.print(text);
    logMsg("Typed: " + text);
    return;
  }

  if (cmd.startsWith("KEY ")) {
    String keyName = cmd.substring(4);
    keyName.trim();
    if (keyName.equalsIgnoreCase("ENTER") || keyName.equalsIgnoreCase("RETURN")) {
      ble.write(KEY_RETURN);
    } else if (keyName.equalsIgnoreCase("ESCAPE") || keyName.equalsIgnoreCase("ESC")) {
      ble.write(KEY_ESC);
    } else if (keyName.equalsIgnoreCase("BACKSPACE")) {
      ble.write(KEY_BACKSPACE);
    } else if (keyName.equalsIgnoreCase("TAB")) {
      ble.write(KEY_TAB);
    } else if (keyName.equalsIgnoreCase("SPACE")) {
      ble.write(' ');
    } else if (keyName.equalsIgnoreCase("HOME")) {
      sendComboKey(KEY_LEFT_GUI, KEY_RETURN);
    } else if (keyName.equalsIgnoreCase("BACK")) {
      ble.write(KEY_ESC);
    } else if (keyName.equalsIgnoreCase("UP")) {
      ble.write(KEY_UP_ARROW);
    } else if (keyName.equalsIgnoreCase("DOWN")) {
      ble.write(KEY_DOWN_ARROW);
    } else if (keyName.equalsIgnoreCase("LEFT")) {
      ble.write(KEY_LEFT_ARROW);
    } else if (keyName.equalsIgnoreCase("RIGHT")) {
      ble.write(KEY_RIGHT_ARROW);
    } else if (keyName.equalsIgnoreCase("GUI") || keyName.equalsIgnoreCase("WIN")) {
      ble.write(KEY_LEFT_GUI);
    } else if (keyName.length() == 1) {
      ble.write(keyName.charAt(0));
    }
    logMsg("Key pressed: " + keyName);
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
        logMsg("Sent Combo: " + modStr + " + " + keyStr);
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
      ble.mouseMove(dx, dy);
    }
    return;
  }

  if (cmd.startsWith("MOUSE_PRESS")) {
    int s1 = cmd.indexOf(' ');
    String btn = "LEFT";
    if (s1 != -1) btn = cmd.substring(s1 + 1);
    btn.trim();
    if (btn.equalsIgnoreCase("RIGHT")) {
      ble.mousePress(MOUSE_RIGHT);
    } else if (btn.equalsIgnoreCase("MIDDLE")) {
      ble.mousePress(MOUSE_MIDDLE);
    } else {
      ble.mousePress(MOUSE_LEFT);
    }
    logMsg("Mouse Press: " + btn);
    return;
  }

  if (cmd.startsWith("MOUSE_RELEASE")) {
    int s1 = cmd.indexOf(' ');
    String btn = "LEFT";
    if (s1 != -1) btn = cmd.substring(s1 + 1);
    btn.trim();
    if (btn.equalsIgnoreCase("RIGHT")) {
      ble.mouseRelease(MOUSE_RIGHT);
    } else if (btn.equalsIgnoreCase("MIDDLE")) {
      ble.mouseRelease(MOUSE_MIDDLE);
    } else {
      ble.mouseRelease(MOUSE_LEFT);
    }
    logMsg("Mouse Release: " + btn);
    return;
  }

  if (cmd.startsWith("MOUSE_SCROLL ")) {
    int wheel = cmd.substring(13).toInt();
    int scrollDist = wheel * 35;
    int steps = max(5, abs(wheel) * 4);
    dragMouse(0, scrollDist, steps, 8);
    logMsg("Mouse Scroll: " + String(wheel));
    return;
  }

  if (cmd.startsWith("MOUSE_CLICK")) {
    int s1 = cmd.indexOf(' ');
    String btn = "LEFT";
    if (s1 != -1) btn = cmd.substring(s1 + 1);
    btn.trim();
    if (btn.equalsIgnoreCase("RIGHT")) {
      ble.mouseClick(MOUSE_RIGHT);
    } else if (btn.equalsIgnoreCase("MIDDLE")) {
      ble.mouseClick(MOUSE_MIDDLE);
    } else {
      ble.mouseClick(MOUSE_LEFT);
    }
    logMsg("Mouse Click: " + btn);
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
    logMsg("Mouse Drag finished");
    return;
  }

  if (cmd.startsWith("DELAY ")) {
    int ms = cmd.substring(6).toInt();
    if (ms > 0 && ms <= 10000) {
      delay(ms);
    }
    return;
  }

  logMsg("Unknown command: " + cmd);
}

// 组合键发送
void sendComboKey(uint8_t modifier, uint8_t key) {
  ble.press(modifier);
  delay(50);
  ble.press(key);
  delay(80);
  ble.releaseAll();
  delay(100);
}

// 鼠标平滑移动
void smoothMouseMove(int totalDx, int totalDy, int steps, int stepDelay) {
  if (steps <= 0) steps = 1;
  int stepX = totalDx / steps;
  int stepY = totalDy / steps;
  for (int i = 0; i < steps; i++) {
    ble.mouseMove(stepX, stepY);
    delay(stepDelay);
  }
}

// 鼠标拖动（模拟手势滑动）
void dragMouse(int dx, int dy, int steps, int stepDelay) {
  if (steps <= 0) steps = 20;
  if (stepDelay <= 0) stepDelay = 15;
  ble.mousePress(MOUSE_LEFT);
  delay(100);
  int stepX = dx / steps;
  int stepY = dy / steps;
  for (int i = 0; i < steps; i++) {
    ble.mouseMove(stepX, stepY);
    delay(stepDelay);
  }
  delay(100);
  ble.mouseRelease(MOUSE_LEFT);
  delay(150);
}

// 唤醒手机屏幕
void wakeUpPhone() {
  logMsg("Waking up phone...");
  ble.write(' ');
  delay(150);
  ble.mouseClick(MOUSE_LEFT);
  delay(300);
}

// 滑动解锁与输入PIN
void unlockScreen(String pin) {
  logMsg("Unlocking screen...");
  dragMouse(0, -600, 30, 15);
  delay(500);

  if (pin.length() > 0) {
    logMsg("Entering PIN code...");
    for (int i = 0; i < pin.length(); i++) {
      ble.write(pin.charAt(i));
      delay(150);
    }
    delay(300);
    ble.write(KEY_RETURN);
    delay(600);
  }
}

// 核心自动化流程：一键开启网络ADB无线调试
void executeAdbFlow(int preset, String pin) {
  if (isRunningFlow) {
    logMsg("Flow already running!");
    return;
  }
  isRunningFlow = true;
  int totalSteps = 6;

  logMsg("Starting Wireless ADB Enable Flow (Preset: " + String(preset) + ")...");

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
    ble.write(KEY_LEFT_GUI);
    delay(400);
    ble.print("settings");
    delay(400);
    ble.write(KEY_RETURN);
  } else if (preset == 1) { // 小米 MIUI / HyperOS
    ble.write(KEY_LEFT_GUI);
    delay(400);
    ble.print("settings");
    delay(400);
    ble.write(KEY_RETURN);
  } else if (preset == 2) { // 华为 HarmonyOS
    sendComboKey(KEY_LEFT_GUI, 'n');
    delay(500);
    ble.write(KEY_LEFT_GUI);
    delay(400);
    ble.print("settings");
    delay(400);
    ble.write(KEY_RETURN);
  } else {
    ble.write(KEY_LEFT_GUI);
    delay(400);
    ble.print("settings");
    delay(400);
    ble.write(KEY_RETURN);
  }
  delay(1200);
  if (!isRunningFlow) return;

  // 第 4 步：在设置中搜索“无线调试”
  reportProgress(4, totalSteps, "搜索无线调试选项");
  sendComboKey(KEY_LEFT_CTRL, 'f');
  delay(400);
  ble.print("wuxiangtiaoshi");
  delay(300);
  ble.write(KEY_BACKSPACE);
  delay(100);
  sendComboKey(KEY_LEFT_CTRL, 'a');
  delay(100);
  ble.print("wireless");
  delay(500);
  ble.write(KEY_RETURN);
  delay(800);
  if (!isRunningFlow) return;

  // 第 5 步：进入无线调试页面并触发开关
  reportProgress(5, totalSteps, "进入并开启无线调试开关");
  ble.write(KEY_DOWN_ARROW);
  delay(200);
  ble.write(KEY_RETURN);
  delay(800);

  ble.write(KEY_RETURN);
  delay(200);
  ble.write(' ');
  delay(500);
  if (!isRunningFlow) return;

  // 第 6 步：确认“是否在此网络上允许无线调试”弹窗
  reportProgress(6, totalSteps, "确认网络调试授权弹窗");
  ble.write(KEY_RIGHT_ARROW);
  delay(200);
  ble.write(KEY_TAB);
  delay(200);
  ble.write(KEY_RETURN);
  delay(200);
  ble.write(' ');

  delay(600);
  isRunningFlow = false;
  reportProgress(6, totalSteps, "完成！无线网络ADB已成功触发开启");
  logMsg("SUCCESS: Wireless ADB enabled flow completed!");
  printDual("[SUCCESS] ADB_ENABLED");
}
