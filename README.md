# ESP32-C3 手机网络 ADB 无线调试控制器 & 蓝牙 HID 脚本引擎

<p align="center">
  <img src="https://img.shields.io/badge/ESP32--C3-BLE%20HID-blue.svg" alt="ESP32-C3 BLE HID">
  <img src="https://img.shields.io/badge/Python-3.8+-green.svg" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-darkblue.svg" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License MIT">
</p>

一套基于 **ESP32-C3 蓝牙 HID 模拟** 与 **PC 端图形化控制台** 的手机自动化控制与网络 ADB（无线调试）自动开启解决方案。

无需手机 Root 权限、无需在手机上安装任何辅助 App，仅通过 ESP32-C3 模拟蓝牙键鼠即可实现：**手机唤醒、滑动屏幕、PIN 码自动解锁、设置页面导航、开启网络 ADB 无线调试、电脑大画板触控映射以及键鼠宏脚本录制回放**。

---

## 🌟 核心特性

- 📱 **免 Root / 免 App 无感控制**：ESP32-C3 伪装为标准蓝牙复合键鼠设备（BLE HID Combo），全平台免驱兼容 Android / iOS。
- ⚡ **一键自动化开启网络 ADB**：内置多机型预设流程（亮屏 -> 解锁 -> 滑屏 -> 设置 -> 开发者选项 -> 开启无线调试）。
- 🎨 **现代化暗黑风上位机**：基于 `CustomTkinter` 构建，支持高分屏自适应、实时状态指示与双串口日志诊断。
- 🖱️ **PC 触控大画板与多模手势**：
  - **🎯 移动光标模式**：按住画板移动鼠标光标，松开立即停止，防漂移设计。
  - **👆 单指划屏模式**：拖拽划屏、翻页与长距离手势滑动。
  - **✋ 拖拽选中模式**：按住左键拖动元素。
  - **🎡 滚轮滚动模式**：模拟上下滚轮浏览。
- 📜 **强大的键鼠宏脚本引擎**：
  - 支持动作实时录制、可视化编辑、单步调试与循环回放。
  - 纯文本脚本格式，方便分享与自定义自动化流程。
- 🔌 **双串口架构支持**：兼容 ESP32-C3 原生 USB CDC 与 板载 CH340 UART0 串口。
- 🛠️ **集成 ADB 工具箱**：内置 ADB 连接扫描、端口测试与一键无线配对连接。

---

## 📂 目录结构

```text
├── firmware/                                    # 固件源码目录
│   └── ESP32_BLE_ADB_Controller/                # Arduino 工程目录
│       └── ESP32_BLE_ADB_Controller.ino         # ESP32-C3 核心固件源码
├── esp32_adb_controller.py                      # PC 客户端主程序 (CustomTkinter GUI)
├── build_exe.bat                               # PC 客户端文件夹式 EXE 打包脚本
├── build_single_exe.bat                        # PC 客户端单文件 EXE 打包脚本
├── requirements.txt                            # Python 依赖清单
├── LICENSE                                     # 开源许可证 (MIT)
└── examples/                                   # 示例宏脚本目录
    └── sample_macro_script.txt                 # 示例键鼠宏脚本
```

---

## 🛠️ 硬件与环境准备

### 1. 硬件需求
- **ESP32-C3 开发板**（带原生 USB 或 CH340 串口均可）。
- **Type-C 数据线** 一根。
- **支持蓝牙的 Android 设备**（需已开启开发者选项并与 ESP32-C3 蓝牙完成配对）。

### 2. 软件环境
- **PC 端**：Windows 10 / 11，Python 3.8+。
- **开发端**：Arduino IDE 2.x（安装 `esp32` 开发板支持包及 `ESP32-BLE-Combo` / `ESP32 BLE Arduino` 库）。

---

## 🚀 快速上手

### 第一步：烧录 ESP32-C3 固件

1. 打开 Arduino IDE，打开 [`firmware/ESP32_BLE_ADB_Controller/ESP32_BLE_ADB_Controller.ino`](firmware/ESP32_BLE_ADB_Controller/ESP32_BLE_ADB_Controller.ino)。
2. 在 **工具 -> 开发板** 中选择 `ESP32C3 Dev Module`。
3. 配置参数建议：
   - **USB CDC On Boot**: `Enabled`
   - **Flash Frequency**: `80MHz`
   - **Upload Speed**: `921600`
4. 编译并烧录至 ESP32-C3 开发板。
5. 打开手机蓝牙，搜索并配对名为 `ESP32-C3 Wireless ADB` 的蓝牙键盘鼠标复合设备。

---

### 第二步：运行 PC 客户端

#### 方式 A：直接运行 Python 源码
```bash
# 1. 克隆本仓库
git clone https://github.com/ghosthgy/esp32-controller.git
cd esp32-controller

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动上位机客户端
python esp32_adb_controller.py
```

#### 方式 B：打包为独立 EXE 文件
双击运行项目根目录下的打包脚本：
- `build_single_exe.bat`：生成单一独立的 `dist/ESP32_ADB_Controller_Single.exe`，便于直接分发运行。
- `build_exe.bat`：生成目录结构的发布版本。

---

## 📖 上位机使用指南

1. **连接开发板**：
   - 插入 ESP32-C3，在客户端顶部下拉框选择对应 COM 口，点击 **“打开串口”**。
   - 确认 **“ESP32 在线”** 与 **“蓝牙已连接”** 状态指示灯变为绿色。
2. **手机一键解锁与 ADB 自动化**：
   - 输入锁屏 PIN 码（如无密码可留空）。
   - 选择对应预设流程（如“亮屏 -> 解锁 -> 打开无线调试”），点击 **“执行预设流程”**。
3. **画板触控映射**：
   - 在右侧大画板中移动鼠标或点击，手机端将实时跟随光标移动。
   - 支持快捷手势与按键触发（返回键、Home键、通知栏、任务管理等）。
4. **宏脚本录制与回放**：
   - 点击 **“开始录制”** 即可在画板或按键操作中录制动作。
   - 录制完成后点击 **“回放脚本”** 或保存为 `.txt` 文件后续载入。

---

## 📝 宏脚本语法规范

脚本为逐行解析的明文指令，支持以下命令：

| 指令 | 参数说明 | 示例 | 描述 |
| :--- | :--- | :--- | :--- |
| `KEY` | `<按键名称/字符>` | `KEY BACK` / `KEY HOME` / `KEY A` | 模拟单击指定按键 |
| `DELAY` | `<毫秒数>` | `DELAY 500` | 延时等待指定时间 |
| `MOUSE_MOVE` | `<dx> <dy>` | `MOUSE_MOVE 10 -20` | 相对移动鼠标坐标 |
| `MOUSE_CLICK` | `<按键类型>` | `MOUSE_CLICK LEFT` | 模拟鼠标按键点击 (LEFT / RIGHT / MIDDLE) |
| `MOUSE_PRESS` | `<按键类型>` | `MOUSE_PRESS LEFT` | 按下鼠标按键不松开 |
| `MOUSE_RELEASE` | `<按键类型>` | `MOUSE_RELEASE LEFT` | 松开鼠标按键 |
| `MOUSE_SCROLL` | `<步数>` | `MOUSE_SCROLL -2` | 滚轮滚动（正数向上，负数向下） |
| `TEXT` | `<字符串>` | `TEXT 123456` | 模拟键盘输入一串字符 |

---

## 📡 串口通信协议

PC 与 ESP32 之间采用波特率 `115200` 纯文本 ASCII 协议：

- **指令格式**：`<CMD> [PARAMS]\n`
- **常用指令**：
  - `STATUS`：查询蓝牙连接与运行状态
  - `FLOW <preset_id> [pin]`：触发预设自动化流程
  - `MM <dx> <dy>`：移动鼠标
  - `MD <dx> <dy> <steps> <delay>`：平滑拖拽移动
  - `MC <1/2/3>`：鼠标点击（1:左键, 2:右键, 3:中键）
  - `KEY <code/char>`：按键触发
  - `TEXT <content>`：输入文本内容

---

## ⚖️ 开源许可证

本项目基于 [MIT License](LICENSE) 开源。允许商业与非商业自由使用、修改与分发。

---

## 🤝 贡献与支持

欢迎提交 Issue 或 Pull Request 完善支持更多品牌手机的自动开启网络 ADB 脚本！如果觉得本项目对你有帮助，欢迎点个 ⭐️ **Star** 支持一下！
