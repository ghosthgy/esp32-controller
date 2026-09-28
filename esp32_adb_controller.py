"""
ESP32-C3 手机网络ADB无线调试智能控制器 - PC客户端 (超大触控画板 & 按住移动光标/松开停止)
"""

import sys
import os
import time
import threading
import subprocess
import socket
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import serial
import serial.tools.list_ports
import customtkinter as ctk

# 设置 CustomTkinter 主题与基础配置
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 统一字体配置 (Windows 首选微软雅黑)
FONT_FAMILY = "Microsoft YaHei UI"
FONT_TITLE = (FONT_FAMILY, 18, "bold")
FONT_CARD_TITLE = (FONT_FAMILY, 14, "bold")
FONT_BOLD = (FONT_FAMILY, 12, "bold")
FONT_REGULAR = (FONT_FAMILY, 11)
FONT_SMALL = (FONT_FAMILY, 10)
FONT_CONSOLE = ("Consolas", 10)


class ADBControllerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ESP32-C3 手机网络ADB控制器 & 鼠标脚本引擎 v2.2 (大画板版)")
        self.geometry("1280, 920")
        self.minsize(1120, 800)

        # 串口通信对象与线程状态
        self.ser = None
        self.serial_thread = None
        self.is_reading_serial = False
        self.ble_connected = False
        self.esp32_connected = False

        # 鼠标录制与交互状态变量
        self.is_recording = False
        self.recording_events = []
        self.is_holding_cursor = False
        self.last_touch_pos = None
        self.last_touch_time = 0
        self.touch_start_time = 0
        self.touch_start_pos = None
        self.live_passthrough = True   # 默认开启实时映射，画板直接控制手机
        self.interaction_mode = "🎯 移动光标 (按住移动/松开停止，不滑动)"

        # 脚本执行状态
        self.is_running_script = False
        self.script_thread = None

        # 初始化界面
        self._build_ui()

        # 启动定时串口扫描
        self._refresh_ports()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ================= 1. 顶部 Header 区域 =================
        self.header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("#2b2b2b", "#1f232a"))
        self.header_frame.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="nsew")
        self.header_frame.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=16, pady=10, sticky="w")

        lbl_title = ctk.CTkLabel(
            title_box,
            text="📱 ESP32-C3 蓝牙控制中心",
            font=FONT_TITLE
        )
        lbl_title.pack(side="left")

        lbl_sub = ctk.CTkLabel(
            title_box,
            text="  |  BLE HID 无线ADB开启 & 超大画板鼠标录制引擎",
            font=FONT_REGULAR,
            text_color="#8c9aa8"
        )
        lbl_sub.pack(side="left", padx=4)

        # 状态指示胶囊
        status_bar = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        status_bar.grid(row=0, column=1, padx=16, pady=10, sticky="e")

        self.card_esp_status = ctk.CTkFrame(status_bar, fg_color=("#3a1d1d", "#331818"), corner_radius=8)
        self.card_esp_status.pack(side="left", padx=6)
        self.lbl_esp_status = ctk.CTkLabel(
            self.card_esp_status,
            text="● ESP32 未连接",
            font=FONT_BOLD,
            text_color="#ff6b6b",
            padx=10,
            pady=3
        )
        self.lbl_esp_status.pack()

        self.card_ble_status = ctk.CTkFrame(status_bar, fg_color=("#2e2e2e", "#25272c"), corner_radius=8)
        self.card_ble_status.pack(side="left", padx=6)
        self.lbl_ble_status = ctk.CTkLabel(
            self.card_ble_status,
            text="○ 手机蓝牙 未就绪",
            font=FONT_BOLD,
            text_color="#a0aab5",
            padx=10,
            pady=3
        )
        self.lbl_ble_status.pack()

        # ================= 2. 常驻顶部：串口连接快捷栏 =================
        self.serial_bar = ctk.CTkFrame(self, corner_radius=10, fg_color=("#242730", "#1a1d24"))
        self.serial_bar.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="nsew")

        lbl_port = ctk.CTkLabel(self.serial_bar, text="🔌 串口端口:", font=FONT_BOLD)
        lbl_port.pack(side="left", padx=(14, 6), pady=8)

        self.port_combo = ctk.CTkComboBox(
            self.serial_bar,
            font=FONT_REGULAR,
            dropdown_font=FONT_REGULAR,
            width=280,
            values=["正在扫描可用串口..."]
        )
        self.port_combo.pack(side="left", padx=(0, 8), pady=8)

        btn_refresh = ctk.CTkButton(
            self.serial_bar,
            text="🔄 刷新",
            width=70,
            font=FONT_REGULAR,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=self._refresh_ports
        )
        btn_refresh.pack(side="left", padx=(0, 10), pady=8)

        self.btn_connect = ctk.CTkButton(
            self.serial_bar,
            text="⚡ 连接 ESP32-C3",
            width=160,
            font=FONT_BOLD,
            command=self._toggle_serial_connect
        )
        self.btn_connect.pack(side="left", padx=(0, 12), pady=8)

        self.lbl_serial_hint = ctk.CTkLabel(
            self.serial_bar,
            text="波特率: 115200 (支持 Native USB CDC / CH340)",
            font=FONT_SMALL,
            text_color="#718096"
        )
        self.lbl_serial_hint.pack(side="right", padx=16, pady=8)

        # ================= 3. 核心功能标签页 (Tabview) =================
        self.tabview = ctk.CTkTabview(self, corner_radius=12)
        self.tabview.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="nsew")

        self.tab_script = self.tabview.add("🖱 1. 手机画板鼠标录制 & 脚本控制")
        self.tab_adb = self.tabview.add("🚀 2. 无线ADB自动开启与调试")

        self._build_script_tab(self.tab_script)
        self._build_adb_tab(self.tab_adb)

    # =========================================================================
    # TAB 1: 鼠标录制与脚本控制中心 (超大画板设计)
    # =========================================================================
    def _build_script_tab(self, parent):
        parent.grid_columnconfigure(0, weight=6)  # 左侧：大幅放大触控画板 (比重6)
        parent.grid_columnconfigure(1, weight=5)  # 右侧：脚本编辑器与控制 (比重5)
        parent.grid_rowconfigure(0, weight=1)

        # ---------------- 1. 左侧：超大手机模拟触控画板 ----------------
        left_box = ctk.CTkFrame(parent, corner_radius=10)
        left_box.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        left_box.grid_rowconfigure(2, weight=1)  # 让中间画板铺满整个高度
        left_box.grid_columnconfigure(0, weight=1)

        # 顶部标题与状态栏
        pad_header = ctk.CTkFrame(left_box, fg_color="transparent")
        pad_header.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="ew")

        ctk.CTkLabel(pad_header, text="📱 超大手机屏幕交互画板", font=FONT_CARD_TITLE).pack(side="left")

        self.lbl_record_status = ctk.CTkLabel(
            pad_header,
            text="● 待机",
            font=FONT_BOLD,
            text_color="#94a3b8"
        )
        self.lbl_record_status.pack(side="right")

        # 模式切换单选器
        mode_box = ctk.CTkFrame(left_box, fg_color="transparent")
        mode_box.grid(row=1, column=0, padx=12, pady=(2, 4), sticky="ew")
        
        self.seg_mode = ctk.CTkSegmentedButton(
            mode_box,
            values=[
                "🎯 移动光标 (按住移动/松开停止，不滑动)",
                "👆 触控拖拽滑动模式"
            ],
            font=FONT_BOLD,
            height=32,
            command=self._on_interaction_mode_changed
        )
        self.seg_mode.set("🎯 移动光标 (按住移动/松开停止，不滑动)")
        self.seg_mode.pack(fill="x")

        # 超大手机屏幕画布 (Canvas)
        canvas_container = ctk.CTkFrame(left_box, fg_color="#101216", corner_radius=14)
        canvas_container.grid(row=2, column=0, padx=12, pady=4, sticky="nsew")
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)

        self.canvas_pad = tk.Canvas(
            canvas_container,
            bg="#141720",
            highlightthickness=2,
            highlightbackground="#2b3142",
            cursor="crosshair"
        )
        self.canvas_pad.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        # 绑定画布事件
        self.canvas_pad.configure(takefocus=1)
        self.canvas_pad.bind("<Configure>", self._draw_phone_frame_decor)
        self.canvas_pad.bind("<Motion>", self._on_canvas_hover_motion)
        self.canvas_pad.bind("<Leave>", self._on_canvas_leave)
        self.canvas_pad.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas_pad.bind("<B1-Motion>", self._on_canvas_b1_motion)
        self.canvas_pad.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas_pad.bind("<Button-3>", self._on_canvas_right_click)
        self.canvas_pad.bind("<MouseWheel>", self._on_canvas_scroll)
        self.canvas_pad.bind("<Key>", self._on_canvas_key_press)

        # 触控板下方操作栏与微调卡片
        pad_controls = ctk.CTkFrame(left_box, fg_color="transparent")
        pad_controls.grid(row=3, column=0, padx=12, pady=(2, 10), sticky="ew")

        # 录制与清空大按钮
        row_rec = ctk.CTkFrame(pad_controls, fg_color="transparent")
        row_rec.pack(fill="x", pady=2)
        row_rec.grid_columnconfigure((0, 1), weight=1)

        self.btn_record_toggle = ctk.CTkButton(
            row_rec,
            text="🔴 开始录制",
            height=36,
            font=FONT_BOLD,
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=self._toggle_recording
        )
        self.btn_record_toggle.grid(row=0, column=0, padx=3, sticky="ew")

        btn_clear_canvas = ctk.CTkButton(
            row_rec,
            text="🧹 清空轨迹",
            height=36,
            font=FONT_REGULAR,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=self._clear_canvas_traces
        )
        btn_clear_canvas.grid(row=0, column=1, padx=3, sticky="ew")

        # 实时映射开关与说明
        row_opts = ctk.CTkFrame(pad_controls, fg_color="transparent")
        row_opts.pack(fill="x", pady=(4, 2))

        self.chk_live_passthrough = ctk.CTkCheckBox(
            row_opts,
            text="实时映射 (画板操作即时同步到手机屏幕)",
            font=FONT_REGULAR,
            command=self._on_live_passthrough_toggle
        )
        self.chk_live_passthrough.select()  # 默认勾选
        self.chk_live_passthrough.pack(side="left", padx=4)

        lbl_guide = ctk.CTkLabel(
            row_opts,
            text="[按住鼠标左键滑行光标 | 画板支持物理键盘方向键]",
            font=FONT_SMALL,
            text_color="#38bdf8"
        )
        lbl_guide.pack(side="right", padx=4)

        # 控制卡片合集容器 (鼠标D-Pad + 键盘方向键)
        pads_holder = ctk.CTkFrame(pad_controls, fg_color=("#1f232a", "#181a22"), corner_radius=8)
        pads_holder.pack(fill="x", pady=(4, 2))

        # 1. 鼠标光标方向盘 (D-Pad)
        d_row1 = ctk.CTkFrame(pads_holder, fg_color="transparent")
        d_row1.pack(fill="x", padx=8, pady=(3, 1))
        d_row1.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(d_row1, text="🕹 鼠标光标微调 & 滚屏:", font=FONT_BOLD).grid(row=0, column=0, columnspan=2, sticky="w")
        
        ctk.CTkLabel(d_row1, text="步长:", font=FONT_SMALL).grid(row=0, column=2, sticky="e", padx=4)
        self.combo_step_size = ctk.CTkComboBox(
            d_row1, width=75, height=24, font=FONT_SMALL,
            values=["10", "30", "60", "120"]
        )
        self.combo_step_size.set("30")
        self.combo_step_size.grid(row=0, column=3, sticky="e")

        d_row2 = ctk.CTkFrame(pads_holder, fg_color="transparent")
        d_row2.pack(fill="x", padx=8, pady=(2, 2))
        d_row2.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)

        btn_up = ctk.CTkButton(d_row2, text="▲ 上移", height=26, font=FONT_SMALL, command=lambda: self._dpad_move(0, -1))
        btn_up.grid(row=0, column=0, padx=1, sticky="ew")

        btn_down = ctk.CTkButton(d_row2, text="▼ 下移", height=26, font=FONT_SMALL, command=lambda: self._dpad_move(0, 1))
        btn_down.grid(row=0, column=1, padx=1, sticky="ew")

        btn_left = ctk.CTkButton(d_row2, text="◀ 左移", height=26, font=FONT_SMALL, command=lambda: self._dpad_move(-1, 0))
        btn_left.grid(row=0, column=2, padx=1, sticky="ew")

        btn_right = ctk.CTkButton(d_row2, text="▶ 右移", height=26, font=FONT_SMALL, command=lambda: self._dpad_move(1, 0))
        btn_right.grid(row=0, column=3, padx=1, sticky="ew")

        btn_d_click = ctk.CTkButton(
            d_row2, text="🔘 单击", height=26, font=FONT_BOLD,
            fg_color="#0284c7", hover_color="#0369a1",
            command=lambda: self._dpad_click("LEFT")
        )
        btn_d_click.grid(row=0, column=4, padx=1, sticky="ew")

        btn_scroll_up = ctk.CTkButton(
            d_row2, text="🔼 滚上", height=26, font=FONT_SMALL,
            fg_color=("#374151", "#252b3b"), hover_color=("#1f2937", "#1a202c"),
            command=lambda: self._dpad_scroll(1)
        )
        btn_scroll_up.grid(row=0, column=5, padx=1, sticky="ew")

        btn_scroll_down = ctk.CTkButton(
            d_row2, text="🔽 滚下", height=26, font=FONT_SMALL,
            fg_color=("#374151", "#252b3b"), hover_color=("#1f2937", "#1a202c"),
            command=lambda: self._dpad_scroll(-1)
        )
        btn_scroll_down.grid(row=0, column=6, padx=1, sticky="ew")

        # 2. 键盘方向导航键控制栏 (Keyboard Direction & Nav Keys)
        k_row1 = ctk.CTkFrame(pads_holder, fg_color="transparent")
        k_row1.pack(fill="x", padx=8, pady=(4, 1))
        ctk.CTkLabel(k_row1, text="⌨ 键盘方向与导航键 (移动菜单焦点/确认):", font=FONT_BOLD).pack(anchor="w")

        k_row2 = ctk.CTkFrame(pads_holder, fg_color="transparent")
        k_row2.pack(fill="x", padx=8, pady=(2, 6))
        k_row2.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1)

        btn_k_up = ctk.CTkButton(
            k_row2, text="⬆ 键盘-上", height=28, font=FONT_SMALL,
            fg_color=("#4338ca", "#3730a3"), hover_color=("#312e81", "#1e1b4b"),
            command=lambda: self._send_keyboard_key("UP")
        )
        btn_k_up.grid(row=0, column=0, padx=2, sticky="ew")

        btn_k_down = ctk.CTkButton(
            k_row2, text="⬇ 键盘-下", height=28, font=FONT_SMALL,
            fg_color=("#4338ca", "#3730a3"), hover_color=("#312e81", "#1e1b4b"),
            command=lambda: self._send_keyboard_key("DOWN")
        )
        btn_k_down.grid(row=0, column=1, padx=2, sticky="ew")

        btn_k_left = ctk.CTkButton(
            k_row2, text="⬅ 键盘-左", height=28, font=FONT_SMALL,
            fg_color=("#4338ca", "#3730a3"), hover_color=("#312e81", "#1e1b4b"),
            command=lambda: self._send_keyboard_key("LEFT")
        )
        btn_k_left.grid(row=0, column=2, padx=2, sticky="ew")

        btn_k_right = ctk.CTkButton(
            k_row2, text="➡ 键盘-右", height=28, font=FONT_SMALL,
            fg_color=("#4338ca", "#3730a3"), hover_color=("#312e81", "#1e1b4b"),
            command=lambda: self._send_keyboard_key("RIGHT")
        )
        btn_k_right.grid(row=0, column=3, padx=2, sticky="ew")

        btn_k_enter = ctk.CTkButton(
            k_row2, text="⏎ 回车", height=28, font=FONT_BOLD,
            fg_color="#059669", hover_color="#047857",
            command=lambda: self._send_keyboard_key("ENTER")
        )
        btn_k_enter.grid(row=0, column=4, padx=2, sticky="ew")

        btn_k_space = ctk.CTkButton(
            k_row2, text="␣ 空格", height=28, font=FONT_BOLD,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=lambda: self._send_keyboard_key("SPACE")
        )
        btn_k_space.grid(row=0, column=5, padx=2, sticky="ew")

        btn_k_tab = ctk.CTkButton(
            k_row2, text="⇥ Tab", height=28, font=FONT_SMALL,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=lambda: self._send_keyboard_key("TAB")
        )
        btn_k_tab.grid(row=0, column=6, padx=2, sticky="ew")

        btn_k_esc = ctk.CTkButton(
            k_row2, text="⎋ 返回/ESC", height=28, font=FONT_SMALL,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=lambda: self._send_keyboard_key("ESC")
        )
        btn_k_esc.grid(row=0, column=7, padx=2, sticky="ew")

        # ---------------- 2. 右侧：脚本编辑器与执行控制 ----------------
        right_box = ctk.CTkFrame(parent, corner_radius=10)
        right_box.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")
        right_box.grid_rowconfigure(2, weight=1)
        right_box.grid_columnconfigure(0, weight=1)

        # 顶部快捷动作与手势
        preset_box = ctk.CTkFrame(right_box, fg_color="transparent")
        preset_box.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        ctk.CTkLabel(preset_box, text="⚡ 常用手势与动作一键插入:", font=FONT_BOLD).pack(anchor="w", pady=(0, 4))

        p_row1 = ctk.CTkFrame(preset_box, fg_color="transparent")
        p_row1.pack(fill="x", pady=2)
        p_row1.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        btn_p_click = ctk.CTkButton(
            p_row1, text="🔘 鼠标单击", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("CLICK")
        )
        btn_p_click.grid(row=0, column=0, padx=2, sticky="ew")

        btn_p_k_up = ctk.CTkButton(
            p_row1, text="⬆ 键盘-上键", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("KEY_UP")
        )
        btn_p_k_up.grid(row=0, column=1, padx=2, sticky="ew")

        btn_p_k_down = ctk.CTkButton(
            p_row1, text="⬇ 键盘-下键", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("KEY_DOWN")
        )
        btn_p_k_down.grid(row=0, column=2, padx=2, sticky="ew")

        btn_p_k_enter = ctk.CTkButton(
            p_row1, text="⏎ 键盘-回车", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("KEY_ENTER")
        )
        btn_p_k_enter.grid(row=0, column=3, padx=2, sticky="ew")

        btn_p_k_space = ctk.CTkButton(
            p_row1, text="␣ 键盘-空格", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("KEY_SPACE")
        )
        btn_p_k_space.grid(row=0, column=4, padx=2, sticky="ew")

        p_row2 = ctk.CTkFrame(preset_box, fg_color="transparent")
        p_row2.pack(fill="x", pady=2)
        p_row2.grid_columnconfigure((0, 1, 2, 3), weight=1)

        btn_p_swipe_up = ctk.CTkButton(
            p_row2, text="📱 短视频上滑", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("SWIPE_UP")
        )
        btn_p_swipe_up.grid(row=0, column=0, padx=2, sticky="ew")

        btn_p_swipe_down = ctk.CTkButton(
            p_row2, text="🔄 下拉刷新", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("SWIPE_DOWN")
        )
        btn_p_swipe_down.grid(row=0, column=1, padx=2, sticky="ew")

        btn_p_sc_up = ctk.CTkButton(
            p_row2, text="🔼 滚屏-向上", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("SCROLL_UP")
        )
        btn_p_sc_up.grid(row=0, column=2, padx=2, sticky="ew")

        btn_p_sc_down = ctk.CTkButton(
            p_row2, text="🔽 滚屏-向下", font=FONT_REGULAR, height=28,
            command=lambda: self._insert_preset("SCROLL_DOWN")
        )
        btn_p_sc_down.grid(row=0, column=3, padx=2, sticky="ew")

        # 脚本文件操作栏
        file_bar = ctk.CTkFrame(right_box, fg_color="transparent")
        file_bar.grid(row=1, column=0, padx=12, pady=(4, 2), sticky="ew")

        ctk.CTkLabel(file_bar, text="📜 脚本代码编辑区:", font=FONT_CARD_TITLE).pack(side="left")

        btn_clear_script = ctk.CTkButton(
            file_bar,
            text="清空代码",
            width=65,
            height=24,
            font=FONT_SMALL,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=self._clear_script_editor
        )
        btn_clear_script.pack(side="right", padx=(4, 0))

        btn_save_script = ctk.CTkButton(
            file_bar,
            text="💾 保存脚本",
            width=75,
            height=24,
            font=FONT_SMALL,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._save_script_to_file
        )
        btn_save_script.pack(side="right", padx=4)

        btn_load_script = ctk.CTkButton(
            file_bar,
            text="📂 打开脚本",
            width=75,
            height=24,
            font=FONT_SMALL,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=self._load_script_from_file
        )
        btn_load_script.pack(side="right", padx=4)

        # 脚本代码文本框
        self.txt_script = ctk.CTkTextbox(
            right_box,
            font=FONT_CONSOLE,
            wrap="none",
            corner_radius=8
        )
        self.txt_script.grid(row=2, column=0, padx=12, pady=(2, 6), sticky="nsew")

        # 初始载入示例脚本
        self._load_demo_script()

        # 脚本执行参数与按钮
        exec_bar = ctk.CTkFrame(right_box, fg_color="transparent")
        exec_bar.grid(row=3, column=0, padx=12, pady=(2, 10), sticky="ew")

        # 循环控制
        loop_row = ctk.CTkFrame(exec_bar, fg_color="transparent")
        loop_row.pack(fill="x", pady=2)

        ctk.CTkLabel(loop_row, text="循环次数:", font=FONT_REGULAR).pack(side="left", padx=(0, 6))
        self.combo_loop_count = ctk.CTkComboBox(
            loop_row,
            width=120,
            font=FONT_REGULAR,
            values=["1 次 (单次)", "3 次", "5 次", "10 次", "无限循环"]
        )
        self.combo_loop_count.set("1 次 (单次)")
        self.combo_loop_count.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(loop_row, text="轮次间歇(ms):", font=FONT_REGULAR).pack(side="left", padx=(0, 6))
        self.entry_loop_delay = ctk.CTkEntry(loop_row, width=80, font=FONT_REGULAR)
        self.entry_loop_delay.insert(0, "800")
        self.entry_loop_delay.pack(side="left")

        # 执行与中止大按钮
        act_row = ctk.CTkFrame(exec_bar, fg_color="transparent")
        act_row.pack(fill="x", pady=(6, 2))

        self.btn_run_script = ctk.CTkButton(
            act_row,
            text="▶ 发送到 ESP32-C3 执行脚本",
            height=40,
            font=FONT_BOLD,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._start_script_execution
        )
        self.btn_run_script.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_stop_script = ctk.CTkButton(
            act_row,
            text="⏹ 中止执行",
            width=85,
            height=40,
            font=FONT_BOLD,
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=self._stop_script_execution
        )
        self.btn_stop_script.pack(side="right")

        # 进度指示
        self.script_progress_bar = ctk.CTkProgressBar(exec_bar, progress_color="#10b981")
        self.script_progress_bar.set(0)
        self.script_progress_bar.pack(fill="x", pady=(6, 2))

        self.lbl_script_status = ctk.CTkLabel(
            exec_bar,
            text="就绪：随时可执行脚本",
            font=FONT_SMALL,
            text_color="#94a3b8"
        )
        self.lbl_script_status.pack(anchor="w")

    # =========================================================================
    # TAB 2: 网络 ADB 自动化与单步调试
    # =========================================================================
    def _build_adb_tab(self, parent):
        parent.grid_columnconfigure(0, weight=5)
        parent.grid_columnconfigure(1, weight=5)
        parent.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkScrollableFrame(parent, label_text="自动化控制与微调", label_font=FONT_CARD_TITLE)
        left_panel.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")

        self._build_auto_flow_card(left_panel)
        self._build_manual_card(left_panel)

        right_panel = ctk.CTkFrame(parent, fg_color="transparent")
        right_panel.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        self._build_adb_helper_card(right_panel)
        self._build_log_card(right_panel)

    def _build_auto_flow_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", padx=4, pady=4)

        lbl = ctk.CTkLabel(card, text="🚀 一键自动化开启网络ADB", font=FONT_CARD_TITLE)
        lbl.pack(anchor="w", padx=12, pady=(8, 4))

        ctk.CTkLabel(card, text="手机系统适配:", font=FONT_REGULAR).pack(anchor="w", padx=12, pady=(2, 2))
        self.preset_combo = ctk.CTkComboBox(
            card,
            font=FONT_REGULAR,
            dropdown_font=FONT_REGULAR,
            values=[
                "0: 原生 Android / Pixel / LineageOS / 通用",
                "1: 小米 / 红米 (MIUI / 澎湃 HyperOS)",
                "2: 华为 / 荣耀 (HarmonyOS / MagicOS)",
                "3: OPPO / 一加 / Realme (ColorOS)",
                "4: VIVO / iQOO (OriginOS)",
                "5: 三星 (OneUI)"
            ]
        )
        self.preset_combo.set("0: 原生 Android / Pixel / LineageOS / 通用")
        self.preset_combo.pack(fill="x", padx=12, pady=(0, 6))

        row_pin = ctk.CTkFrame(card, fg_color="transparent")
        row_pin.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(row_pin, text="锁屏密码 (PIN):", font=FONT_REGULAR).pack(side="left", padx=(0, 6))
        self.entry_pin = ctk.CTkEntry(
            row_pin,
            placeholder_text="若无锁屏密码请留空",
            font=FONT_REGULAR
        )
        self.entry_pin.pack(side="left", fill="x", expand=True)

        row_act = ctk.CTkFrame(card, fg_color="transparent")
        row_act.pack(fill="x", padx=12, pady=(8, 4))

        self.btn_run_flow = ctk.CTkButton(
            row_act,
            text="▶ 一键执行流程",
            height=38,
            font=FONT_BOLD,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._start_adb_flow
        )
        self.btn_run_flow.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_stop_flow = ctk.CTkButton(
            row_act,
            text="⏹ 中止",
            width=65,
            height=38,
            font=FONT_BOLD,
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=self._stop_adb_flow
        )
        self.btn_stop_flow.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(card, progress_color="#10b981")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(6, 2))

        self.lbl_progress_desc = ctk.CTkLabel(
            card,
            text="就绪：等待触发",
            font=FONT_REGULAR,
            text_color="#94a3b8"
        )
        self.lbl_progress_desc.pack(anchor="w", padx=12, pady=(0, 8))

    def _build_manual_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", padx=4, pady=4)

        lbl = ctk.CTkLabel(card, text="🎮 手动微调与单步控制", font=FONT_CARD_TITLE)
        lbl.pack(anchor="w", padx=12, pady=(8, 4))

        grid_frame = ctk.CTkFrame(card, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=2)
        grid_frame.grid_columnconfigure((0, 1), weight=1)

        btn_wake = ctk.CTkButton(
            grid_frame,
            text="💡 唤醒屏幕",
            font=FONT_REGULAR,
            command=lambda: self._send_cmd("WAKE")
        )
        btn_wake.grid(row=0, column=0, padx=4, pady=3, sticky="ew")

        btn_unlock = ctk.CTkButton(
            grid_frame,
            text="👆 上滑解锁",
            font=FONT_REGULAR,
            command=lambda: self._send_cmd("UNLOCK " + self.entry_pin.get().strip())
        )
        btn_unlock.grid(row=0, column=1, padx=4, pady=3, sticky="ew")

        btn_settings = ctk.CTkButton(
            grid_frame,
            text="⚙ 打开系统设置",
            font=FONT_REGULAR,
            command=lambda: self._open_settings_step()
        )
        btn_settings.grid(row=1, column=0, padx=4, pady=3, sticky="ew")

        btn_search = ctk.CTkButton(
            grid_frame,
            text="🔍 搜索无线调试",
            font=FONT_REGULAR,
            command=lambda: self._search_adb_step()
        )
        btn_search.grid(row=1, column=1, padx=4, pady=3, sticky="ew")

        btn_toggle = ctk.CTkButton(
            grid_frame,
            text="🔘 切换开关 (Enter)",
            font=FONT_REGULAR,
            command=lambda: self._send_cmd("KEY ENTER")
        )
        btn_toggle.grid(row=2, column=0, padx=4, pady=3, sticky="ew")

        btn_allow = ctk.CTkButton(
            grid_frame,
            text="✅ 确认允许弹窗",
            font=FONT_REGULAR,
            command=lambda: self._confirm_dialog_step()
        )
        btn_allow.grid(row=2, column=1, padx=4, pady=3, sticky="ew")

        btn_home = ctk.CTkButton(
            grid_frame,
            text="🏠 回到桌面 (Home)",
            font=FONT_REGULAR,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=lambda: self._send_cmd("KEY HOME")
        )
        btn_home.grid(row=3, column=0, padx=4, pady=3, sticky="ew")

        btn_back = ctk.CTkButton(
            grid_frame,
            text="↩ 返回上一级 (Back)",
            font=FONT_REGULAR,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=lambda: self._send_cmd("KEY BACK")
        )
        btn_back.grid(row=3, column=1, padx=4, pady=3, sticky="ew")

        text_row = ctk.CTkFrame(card, fg_color="transparent")
        text_row.pack(fill="x", padx=10, pady=(6, 8))

        self.entry_custom_text = ctk.CTkEntry(
            text_row,
            placeholder_text="输入英文字符直接发送到手机...",
            font=FONT_REGULAR
        )
        self.entry_custom_text.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_send_text = ctk.CTkButton(
            text_row,
            text="发送文本",
            width=75,
            font=FONT_REGULAR,
            command=lambda: self._send_custom_text()
        )
        btn_send_text.pack(side="right")

    def _build_adb_helper_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=0, padx=0, pady=(0, 6), sticky="nsew")

        lbl = ctk.CTkLabel(card, text="🌐 ADB 网络无线连接助手", font=FONT_CARD_TITLE)
        lbl.pack(anchor="w", padx=12, pady=(8, 4))

        ip_row = ctk.CTkFrame(card, fg_color="transparent")
        ip_row.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(ip_row, text="手机 IP:端口:", font=FONT_REGULAR).pack(side="left", padx=(0, 6))
        self.entry_phone_ip = ctk.CTkEntry(
            ip_row,
            placeholder_text="192.168.x.x:5555",
            font=FONT_REGULAR
        )
        self.entry_phone_ip.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_scan_ip = ctk.CTkButton(
            ip_row,
            text="🔍 自动嗅探",
            width=75,
            font=FONT_REGULAR,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=self._auto_scan_phone_ip
        )
        btn_scan_ip.pack(side="right")

        btn_grid = ctk.CTkFrame(card, fg_color="transparent")
        btn_grid.pack(fill="x", padx=10, pady=(4, 8))
        btn_grid.grid_columnconfigure((0, 1), weight=1)

        btn_adb_connect = ctk.CTkButton(
            btn_grid,
            text="🔗 执行 adb connect",
            font=FONT_BOLD,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._run_adb_connect
        )
        btn_adb_connect.grid(row=0, column=0, padx=4, pady=3, sticky="ew")

        btn_adb_devices = ctk.CTkButton(
            btn_grid,
            text="📱 adb devices",
            font=FONT_REGULAR,
            command=self._run_adb_devices
        )
        btn_adb_devices.grid(row=0, column=1, padx=4, pady=3, sticky="ew")

        btn_adb_shell = ctk.CTkButton(
            btn_grid,
            text="💻 打开 ADB Shell",
            font=FONT_REGULAR,
            command=self._open_adb_shell
        )
        btn_adb_shell.grid(row=1, column=0, padx=4, pady=3, sticky="ew")

        btn_scrcpy = ctk.CTkButton(
            btn_grid,
            text="🖥 启动 Scrcpy 投屏",
            font=FONT_REGULAR,
            command=self._launch_scrcpy
        )
        btn_scrcpy.grid(row=1, column=1, padx=4, pady=3, sticky="ew")

    def _build_log_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=1, column=0, padx=0, pady=(6, 0), sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        head_row = ctk.CTkFrame(card, fg_color="transparent")
        head_row.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")

        lbl = ctk.CTkLabel(head_row, text="📋 实时通信与执行日志", font=FONT_CARD_TITLE)
        lbl.pack(side="left")

        btn_clear = ctk.CTkButton(
            head_row,
            text="清空日志",
            width=65,
            height=24,
            font=FONT_SMALL,
            fg_color=("#4a5568", "#334155"),
            hover_color=("#2d3748", "#1e293b"),
            command=self._clear_log
        )
        btn_clear.pack(side="right")

        self.txt_log = ctk.CTkTextbox(
            card,
            font=FONT_CONSOLE,
            wrap="word",
            corner_radius=8
        )
        self.txt_log.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")

    # =========================================================================
    # 触控画板绘图与光标交互核心逻辑
    # =========================================================================
    def _on_interaction_mode_changed(self, mode):
        self.interaction_mode = mode
        if "移动光标" in mode:
            self._log("🎯 模式：【光标移动 (按住滑行/松开停止)】按住鼠标左键在画板滑行即可移动手机光标，不会拖拽屏幕！")
        else:
            self._log("👆 模式：【触控拖拽滑动】按住左键在画板拖拽将模拟手指拖动滑动屏幕。")

    def _draw_phone_frame_decor(self, event=None):
        w = self.canvas_pad.winfo_width()
        h = self.canvas_pad.winfo_height()
        if w <= 20 or h <= 20:
            return

        self.canvas_pad.delete("decor")

        # 绘制顶部听筒/灵动岛
        self.canvas_pad.create_oval(w / 2 - 20, 12, w / 2 + 20, 24, fill="#232736", outline="", tags="decor")
        self.canvas_pad.create_oval(w / 2 - 4, 16, w / 2 + 4, 20, fill="#38bdf8", outline="", tags="decor")

        # 绘制底部 Home 条
        self.canvas_pad.create_rectangle(w / 2 - 60, h - 18, w / 2 + 60, h - 14, fill="#3b4256", outline="", tags="decor")

        # 绘制背景参考网格虚线
        for y_line in range(50, h - 40, 60):
            self.canvas_pad.create_line(20, y_line, w - 20, y_line, fill="#181c28", dash=(2, 6), tags="decor")
        for x_line in range(50, w - 40, 60):
            self.canvas_pad.create_line(x_line, 30, x_line, h - 30, fill="#181c28", dash=(2, 6), tags="decor")

    def _toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.recording_events = []
            self.btn_record_toggle.configure(
                text="⏹ 停止录制",
                fg_color="#eab308",
                hover_color="#ca8a04"
            )
            self.lbl_record_status.configure(text="🔴 录制中...", text_color="#ef4444")
            self._log("🔴 开启录制：请在画板上【按住鼠标移动光标】或点击按钮，动作将自动生成脚本...")
        else:
            self.is_recording = False
            self.btn_record_toggle.configure(
                text="🔴 开始录制",
                fg_color="#ef4444",
                hover_color="#dc2626"
            )
            self.lbl_record_status.configure(text=f"● 录制完成 ({len(self.recording_events)} 步)", text_color="#10b981")
            self._log(f"录制完成，已记录 {len(self.recording_events)} 个动作指令。")

    # 鼠标悬停在画板上 (显示指针标记)
    def _on_canvas_hover_motion(self, event):
        self.canvas_pad.delete("hover_mark")
        r = 7
        self.canvas_pad.create_oval(
            event.x - r, event.y - r, event.x + r, event.y + r,
            outline="#38bdf8", width=1.5, tags="hover_mark"
        )
        self.canvas_pad.create_line(event.x - r - 4, event.y, event.x + r + 4, event.y, fill="#38bdf8", tags="hover_mark")
        self.canvas_pad.create_line(event.x, event.y - r - 4, event.x, event.y + r + 4, fill="#38bdf8", tags="hover_mark")

    def _on_canvas_leave(self, event):
        self.canvas_pad.delete("hover_mark")
        self.last_touch_pos = None

    # 按下鼠标左键：按住开始移动光标
    def _on_canvas_press(self, event):
        now = time.time()
        self.is_holding_cursor = True
        self.last_touch_pos = (event.x, event.y)
        self.touch_start_pos = (event.x, event.y)
        self.last_touch_time = now
        self.touch_start_time = now

        # 画布视觉特效 (光标激活标记)
        self.canvas_pad.create_oval(
            event.x - 12, event.y - 12, event.x + 12, event.y + 12,
            outline="#06b6d4", width=2, fill="#083344", tags="trace"
        )

        if "移动光标" not in self.interaction_mode:
            # 触控拖拽滑动模式：发送并记录按下
            if self.live_passthrough and self.ble_connected:
                self._send_cmd("MOUSE_PRESS LEFT")
            if self.is_recording:
                self._append_script_line("MOUSE_PRESS LEFT")
                self.recording_events.append("MOUSE_PRESS LEFT")

    # 按住拖动：移动光标 (不滑动屏幕) 或 拖拽滑动
    def _on_canvas_b1_motion(self, event):
        if self.last_touch_pos is None:
            self.last_touch_pos = (event.x, event.y)
            self.last_touch_time = time.time()
            return

        now = time.time()
        dx = event.x - self.last_touch_pos[0]
        dy = event.y - self.last_touch_pos[1]
        dt_ms = int((now - self.last_touch_time) * 1000)

        # 过滤极微小抖动
        if abs(dx) < 1 and abs(dy) < 1:
            return

        if "移动光标" in self.interaction_mode:
            # 🎯 移动光标模式：只发送 MOUSE_MOVE，绝不发送 MOUSE_PRESS，纯移动光标不滑动！
            self.canvas_pad.create_line(
                self.last_touch_pos[0], self.last_touch_pos[1],
                event.x, event.y,
                fill="#38bdf8", width=2.5, capstyle="round", tags="trace"
            )

            if dt_ms >= 12:
                if self.is_recording:
                    self._append_script_line(f"DELAY {min(dt_ms, 300)}")
                    self._append_script_line(f"MOUSE_MOVE {dx} {dy}")
                    self.recording_events.append(f"MOUSE_MOVE {dx} {dy}")

                if self.live_passthrough and self.ble_connected:
                    self._send_cmd(f"MOUSE_MOVE {dx} {dy}")

                self.last_touch_pos = (event.x, event.y)
                self.last_touch_time = now
        else:
            # 👆 触控拖拽滑动模式：绿色拖拽轨迹
            self.canvas_pad.create_line(
                self.last_touch_pos[0], self.last_touch_pos[1],
                event.x, event.y,
                fill="#10b981", width=3.5, capstyle="round", tags="trace"
            )

            if dt_ms >= 12:
                if self.is_recording:
                    self._append_script_line(f"DELAY {min(dt_ms, 500)}")
                    self._append_script_line(f"MOUSE_MOVE {dx} {dy}")
                    self.recording_events.append(f"MOUSE_MOVE {dx} {dy}")

                if self.live_passthrough and self.ble_connected:
                    self._send_cmd(f"MOUSE_MOVE {dx} {dy}")

                self.last_touch_pos = (event.x, event.y)
                self.last_touch_time = now

    # 松开鼠标左键：松开停止
    def _on_canvas_release(self, event):
        self.is_holding_cursor = False
        now = time.time()
        total_dt = now - self.touch_start_time

        # 如果在光标移动模式下，几乎原地按下并立即松开（<0.25s且位移<5px），则触发一次单击
        is_tap = False
        if self.touch_start_pos:
            dist = ((event.x - self.touch_start_pos[0])**2 + (event.y - self.touch_start_pos[1])**2)**0.5
            if dist < 6 and total_dt < 0.28:
                is_tap = True

        if "移动光标" in self.interaction_mode:
            if is_tap:
                # 触发精准单击当前按钮
                self.canvas_pad.create_oval(
                    event.x - 8, event.y - 8, event.x + 8, event.y + 8,
                    fill="#38bdf8", outline="", tags="trace"
                )
                if self.live_passthrough and self.ble_connected:
                    self._send_cmd("MOUSE_CLICK LEFT")
                if self.is_recording:
                    self._append_script_line("MOUSE_CLICK LEFT")
                    self._append_script_line("DELAY 400")
                    self.recording_events.append("MOUSE_CLICK LEFT")
            else:
                # 仅滑行结束，在终点绘制标记
                self.canvas_pad.create_oval(
                    event.x - 6, event.y - 6, event.x + 6, event.y + 6,
                    outline="#38bdf8", width=2, tags="trace"
                )
        else:
            # 触控拖拽滑动模式：释放按键
            if self.live_passthrough and self.ble_connected:
                self._send_cmd("MOUSE_RELEASE LEFT")
            if self.is_recording:
                self._append_script_line("MOUSE_RELEASE LEFT")
                self._append_script_line("DELAY 400")
                self.recording_events.append("MOUSE_RELEASE LEFT")

        self.last_touch_pos = None
        self.touch_start_pos = None

    def _on_canvas_right_click(self, event):
        # 右键模拟返回
        self.canvas_pad.create_oval(
            event.x - 6, event.y - 6, event.x + 6, event.y + 6,
            fill="#f59e0b", outline="", tags="trace"
        )
        if self.live_passthrough and self.ble_connected:
            self._send_cmd("KEY BACK")

        if self.is_recording:
            self._append_script_line("KEY BACK")
            self._append_script_line("DELAY 500")
            self.recording_events.append("KEY BACK")

    def _on_canvas_scroll(self, event):
        steps = 1 if event.delta > 0 else -1
        if self.live_passthrough and self.ble_connected:
            self._send_cmd(f"MOUSE_SCROLL {steps * 2}")

        if self.is_recording:
            self._append_script_line(f"MOUSE_SCROLL {steps * 2}")
            self._append_script_line("DELAY 100")
            self.recording_events.append(f"MOUSE_SCROLL {steps * 2}")

    # 方向微调控制器 (D-Pad)
    def _dpad_move(self, dir_x, dir_y):
        try:
            step = int(self.combo_step_size.get())
        except ValueError:
            step = 30

        dx = dir_x * step
        dy = dir_y * step

        if self.live_passthrough or self.esp32_connected:
            self._send_cmd(f"MOUSE_MOVE {dx} {dy}")

        if self.is_recording:
            self._append_script_line("DELAY 80")
            self._append_script_line(f"MOUSE_MOVE {dx} {dy}")
            self.recording_events.append(f"MOUSE_MOVE {dx} {dy}")

    def _dpad_click(self, btn="LEFT"):
        if self.live_passthrough or self.esp32_connected:
            self._send_cmd(f"MOUSE_CLICK {btn}")

        if self.is_recording:
            self._append_script_line(f"MOUSE_CLICK {btn}")
            self._append_script_line("DELAY 400")
            self.recording_events.append(f"MOUSE_CLICK {btn}")

    def _dpad_scroll(self, direction):
        try:
            val = int(self.combo_scroll_step.get().split(" ")[0])
        except (ValueError, IndexError):
            val = 1
        steps = direction * val
        if self.live_passthrough or self.esp32_connected:
            self._send_cmd(f"MOUSE_SCROLL {steps}")

        if self.is_recording:
            self._append_script_line("DELAY 150")
            self._append_script_line(f"MOUSE_SCROLL {steps}")
            self.recording_events.append(f"MOUSE_SCROLL {steps}")

    # 发送并录制键盘按键
    def _send_keyboard_key(self, key_name):
        key_name = key_name.upper()
        if self.live_passthrough or self.esp32_connected:
            self._send_cmd(f"KEY {key_name}")

        if self.is_recording:
            self._append_script_line("DELAY 150")
            self._append_script_line(f"KEY {key_name}")
            self.recording_events.append(f"KEY {key_name}")

    # 捕获物理键盘按键事件 (当画板获得焦点时)
    def _on_canvas_key_press(self, event):
        key_map = {
            "Up": "UP",
            "Down": "DOWN",
            "Left": "LEFT",
            "Right": "RIGHT",
            "Return": "ENTER",
            "KP_Enter": "ENTER",
            "Tab": "TAB",
            "Escape": "ESC",
            "BackSpace": "BACKSPACE",
            "space": "SPACE",
            "Home": "HOME"
        }
        key_name = key_map.get(event.keysym)
        if key_name:
            self._send_keyboard_key(key_name)
            # 在画板上绘制按键悬浮标记
            w = self.canvas_pad.winfo_width()
            h = self.canvas_pad.winfo_height()
            self.canvas_pad.delete("key_badge")
            self.canvas_pad.create_rectangle(
                w / 2 - 60, h / 2 - 16, w / 2 + 60, h / 2 + 16,
                fill="#1e1b4b", outline="#818cf8", width=1.5, tags="key_badge"
            )
            self.canvas_pad.create_text(
                w / 2, h / 2, text=f"⌨ KEY: {key_name}", fill="#e0e7ff",
                font=("Consolas", 11, "bold"), tags="key_badge"
            )
            self.after(400, lambda: self.canvas_pad.delete("key_badge"))

    def _clear_canvas_traces(self):
        self.canvas_pad.delete("trace")
        self.canvas_pad.delete("hover_mark")
        self.canvas_pad.delete("key_badge")

    def _on_live_passthrough_toggle(self):
        self.live_passthrough = bool(self.chk_live_passthrough.get())
        if self.live_passthrough:
            self._log("⚡ 已启用实时映射：画板操作将即时同步至手机蓝牙！")
        else:
            self._log("已关闭画板实时映射。")

    # =========================================================================
    # 脚本编辑器与预设手势
    # =========================================================================
    def _append_script_line(self, line):
        self.txt_script.insert("end", line + "\n")
        self.txt_script.see("end")

    def _clear_script_editor(self):
        self.txt_script.delete("1.0", "end")

    def _insert_preset(self, preset_type):
        presets = {
            "CLICK": "# 点击当前光标位置\nMOUSE_CLICK LEFT\nDELAY 500\n",
            "KEY_UP": "# 键盘方向键-上\nKEY UP\nDELAY 200\n",
            "KEY_DOWN": "# 键盘方向键-下\nKEY DOWN\nDELAY 200\n",
            "KEY_ENTER": "# 键盘回车确认\nKEY ENTER\nDELAY 500\n",
            "KEY_SPACE": "# 键盘空格键\nKEY SPACE\nDELAY 300\n",
            "KEY_TAB": "# 键盘Tab切换焦点\nKEY TAB\nDELAY 300\n",
            "SCROLL_UP": "# 向上轻微滚屏\nMOUSE_SCROLL 1\nDELAY 300\n",
            "SCROLL_DOWN": "# 向下轻微滚屏\nMOUSE_SCROLL -1\nDELAY 300\n",
            "SWIPE_UP": "# 短视频快速上滑翻页\nMOUSE_DRAG 0 -600 25 12\nDELAY 1000\n",
            "SWIPE_DOWN": "# 下拉刷新页面\nMOUSE_DRAG 0 600 25 12\nDELAY 1200\n",
            "DBL_CLICK": "# 双击屏幕 (点赞)\nMOUSE_CLICK LEFT\nDELAY 100\nMOUSE_CLICK LEFT\nDELAY 800\n",
            "LONG_PRESS": "# 屏幕长按 1.5 秒\nMOUSE_PRESS LEFT\nDELAY 1500\nMOUSE_RELEASE LEFT\nDELAY 500\n",
            "HOME": "# 回到主屏幕 (Home 键)\nKEY HOME\nDELAY 500\n",
            "BACK": "# 返回上一级 (Back 键)\nKEY BACK\nDELAY 500\n"
        }
        text = presets.get(preset_type, "")
        if text:
            self._append_script_line(text.strip())

    def _load_demo_script(self):
        demo = """# ESP32-C3 手机控制自动化脚本示例
# 支持指令: MOUSE_MOVE, MOUSE_CLICK, MOUSE_PRESS, MOUSE_RELEASE, MOUSE_DRAG, DELAY, KEY, TYPE

# 1. 唤醒并解锁屏幕
WAKE
DELAY 600
MOUSE_DRAG 0 -600 25 15
DELAY 800

# 2. 打开系统设置并搜索无线调试
KEY GUI
DELAY 400
TYPE settings
DELAY 400
KEY ENTER
DELAY 1200

# 3. 滑行光标对准并点击开启无线调试按钮
MOUSE_MOVE 0 160
DELAY 300
MOUSE_CLICK LEFT
DELAY 800
"""
        self.txt_script.delete("1.0", "end")
        self.txt_script.insert("1.0", demo)

    def _save_script_to_file(self):
        content = self.txt_script.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showwarning("提示", "脚本内容为空，无法保存！")
            return

        file_path = filedialog.asksaveasfilename(
            title="保存脚本文件",
            defaultextension=".txt",
            filetypes=[("Text Script", "*.txt"), ("ESP32 Script", "*.esp"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self._log(f"💾 脚本已成功保存至: {file_path}")
                messagebox.showinfo("成功", "脚本文件保存成功！")
            except Exception as e:
                self._log(f"保存脚本失败: {str(e)}")
                messagebox.showerror("错误", f"保存脚本失败: {str(e)}")

    def _load_script_from_file(self):
        file_path = filedialog.askopenfilename(
            title="打开脚本文件",
            filetypes=[("Script Files", "*.txt;*.esp"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_script.delete("1.0", "end")
                self.txt_script.insert("1.0", content)
                self._log(f"📂 成功加载脚本文件: {file_path}")
            except Exception as e:
                self._log(f"打开脚本失败: {str(e)}")
                messagebox.showerror("错误", f"读取脚本文件失败: {str(e)}")

    # =========================================================================
    # 脚本解析与 ESP32 发送执行引擎
    # =========================================================================
    def _start_script_execution(self):
        if self.is_running_script:
            self._log("提示: 脚本正在运行中！")
            return

        if not self.esp32_connected:
            self._log("错误: ESP32-C3 尚未连接，请先连接串口！")
            messagebox.showwarning("未连接", "请先连接 ESP32-C3 串口设备！")
            return

        content = self.txt_script.get("1.0", "end-1c")
        lines = [line.strip() for line in content.split("\n")]
        valid_commands = [line for line in lines if line and not line.startswith("#") and not line.startswith("//")]

        if not valid_commands:
            self._log("错误: 脚本中没有可执行的指令！")
            return

        loop_str = self.combo_loop_count.get()
        if "无限" in loop_str:
            total_loops = -1
        else:
            match = re.search(r'(\d+)', loop_str)
            total_loops = int(match.group(1)) if match else 1

        try:
            loop_delay_ms = max(0, int(self.entry_loop_delay.get().strip()))
        except ValueError:
            loop_delay_ms = 500

        self.is_running_script = True
        self.btn_run_script.configure(state="disabled", fg_color="#6b7280")
        self.btn_stop_script.configure(state="normal")
        self.script_progress_bar.set(0)

        self._log(f"🚀 开始执行脚本 (有效指令数: {len(valid_commands)}, 循环设置: {loop_str})...")

        self.script_thread = threading.Thread(
            target=self._script_executor_worker,
            args=(valid_commands, total_loops, loop_delay_ms),
            daemon=True
        )
        self.script_thread.start()

    def _stop_script_execution(self):
        if self.is_running_script:
            self.is_running_script = False
            self._log("⏹ 正在中止脚本执行...")
            self.lbl_script_status.configure(text="已手动中止")
            self._send_cmd("MOUSE_RELEASE LEFT")

    def _script_executor_worker(self, commands, total_loops, loop_delay_ms):
        current_loop = 0
        total_cmd_count = len(commands)

        while self.is_running_script:
            current_loop += 1
            loop_info = f"第 {current_loop} 轮" if total_loops != 1 else "执行中"
            if total_loops > 0:
                loop_info = f"第 {current_loop}/{total_loops} 轮"

            for idx, cmd in enumerate(commands):
                if not self.is_running_script:
                    break

                progress = (idx + 1) / total_cmd_count
                self.after(0, self._update_script_progress, progress, f"{loop_info} - [{idx+1}/{total_cmd_count}] {cmd}")

                if cmd.upper().startswith("DELAY "):
                    try:
                        ms = int(cmd.split(" ")[1])
                        chunks = ms // 50
                        rem = ms % 50
                        for _ in range(chunks):
                            if not self.is_running_script:
                                break
                            time.sleep(0.05)
                        if self.is_running_script and rem > 0:
                            time.sleep(rem / 1000.0)
                    except Exception:
                        time.sleep(0.1)
                else:
                    self._send_cmd(cmd)
                    time.sleep(0.02)

            if not self.is_running_script:
                break

            if total_loops > 0 and current_loop >= total_loops:
                break

            if loop_delay_ms > 0:
                chunks = loop_delay_ms // 50
                for _ in range(chunks):
                    if not self.is_running_script:
                        break
                    time.sleep(0.05)

        self.after(0, self._on_script_finished)

    def _update_script_progress(self, progress, status_text):
        self.script_progress_bar.set(progress)
        self.lbl_script_status.configure(text=status_text)

    def _on_script_finished(self):
        self.is_running_script = False
        self.btn_run_script.configure(state="normal", fg_color="#10b981")
        self.btn_stop_script.configure(state="normal")
        self.script_progress_bar.set(1.0)
        self.lbl_script_status.configure(text="✅ 脚本执行完成")
        self._log("🎉 脚本全部指令执行完毕！")

    # =========================================================================
    # 通用串口通信与 ADB 工具
    # =========================================================================
    def _log(self, text):
        timestamp = time.strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{timestamp}] {text}\n")
        self.txt_log.see("end")

    def _clear_log(self):
        self.txt_log.delete("1.0", "end")

    def _refresh_ports(self):
        ports = list(serial.tools.list_ports.comports())
        port_list = []
        best_match = None

        for p in ports:
            desc = f"{p.device} ({p.description})"
            port_list.append(desc)
            if any(k in p.description.lower() for k in ["ch340", "cp210", "esp32", "usb serial", "jtag", "uart"]):
                best_match = desc

        if not port_list:
            port_list = ["未检测到串口设备"]
            self.port_combo.configure(values=port_list)
            self.port_combo.set("未检测到串口设备")
        else:
            self.port_combo.configure(values=port_list)
            if best_match:
                self.port_combo.set(best_match)
            else:
                self.port_combo.set(port_list[0])

    def _toggle_serial_connect(self):
        if self.ser and self.ser.is_open:
            self._disconnect_serial()
        else:
            self._connect_serial()

    def _connect_serial(self):
        selected = self.port_combo.get()
        if "未检测到串口设备" in selected or not selected:
            self._log("错误: 请先选择有效的 ESP32-C3 串口！")
            return

        port_name = selected.split(" ")[0]
        try:
            self._log(f"正在连接串口 {port_name} (波特率 115200)...")
            self.ser = serial.Serial(port_name, 115200, timeout=1)
            self.esp32_connected = True
            self.btn_connect.configure(
                text="❌ 断开连接",
                fg_color="#ef4444",
                hover_color="#dc2626"
            )
            self.card_esp_status.configure(fg_color=("#183321", "#152e1e"))
            self.lbl_esp_status.configure(text=f"● ESP32 已连接 ({port_name})", text_color="#10b981")
            self._log(f"串口 {port_name} 连接成功！")

            self.is_reading_serial = True
            self.serial_thread = threading.Thread(target=self._serial_reader_loop, daemon=True)
            self.serial_thread.start()

            self._send_cmd("PING")
            self._send_cmd("STATUS")

        except Exception as e:
            self._log(f"连接串口失败: {str(e)}")
            self._disconnect_serial()

    def _disconnect_serial(self):
        self.is_reading_serial = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        self.esp32_connected = False
        self.ble_connected = False
        self.btn_connect.configure(
            text="⚡ 连接 ESP32-C3",
            fg_color=["#3a7ebf", "#1f538d"],
            hover_color=["#325882", "#14375e"]
        )
        self.card_esp_status.configure(fg_color=("#3a1d1d", "#331818"))
        self.lbl_esp_status.configure(text="● ESP32 未连接", text_color="#ff6b6b")

        self.card_ble_status.configure(fg_color=("#2e2e2e", "#25272c"))
        self.lbl_ble_status.configure(text="○ 手机蓝牙 未就绪", text_color="#a0aab5")
        self._log("串口已断开。")

    def _serial_reader_loop(self):
        while self.is_reading_serial and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    self.after(0, self._handle_serial_incoming, line)
            except Exception:
                break
        self.after(0, self._on_serial_disconnected)

    def _on_serial_disconnected(self):
        if self.esp32_connected:
            self._log("串口通信中断。")
            self._disconnect_serial()

    def _handle_serial_incoming(self, line):
        if line == "PONG":
            self._log("ESP32 握手响应: PONG (通信正常)")
            return

        if "[STATUS]" in line:
            if "BLE:1" in line:
                self.ble_connected = True
                self.card_ble_status.configure(fg_color=("#183321", "#152e1e"))
                self.lbl_ble_status.configure(text="● 手机蓝牙 已连接", text_color="#10b981")
            elif "BLE:0" in line:
                self.ble_connected = False
                self.card_ble_status.configure(fg_color=("#362e15", "#2e2712"))
                self.lbl_ble_status.configure(text="○ 手机蓝牙 等待配对", text_color="#f59e0b")
            return

        if "[PROGRESS]" in line:
            match = re.search(r'\[PROGRESS\]\s+(\d+)/(\d+)\s+(.+)', line)
            if match:
                curr = int(match.group(1))
                total = int(match.group(2))
                desc = match.group(3)
                self.progress_bar.set(curr / total)
                self.lbl_progress_desc.configure(text=f"步骤 {curr}/{total}: {desc}")
                self._log(f"⚡ 进度: ({curr}/{total}) {desc}")
            return

        if "[SUCCESS] ADB_ENABLED" in line:
            self.progress_bar.set(1.0)
            self.lbl_progress_desc.configure(text="✅ 成功完成！手机无线网络ADB已开启")
            self._log("🎉 成功开启手机网络ADB无线调试！")
            return

        if "[LOG]" in line:
            clean = line.replace("[LOG]", "").strip()
            self._log(f"ESP32: {clean}")
            return

        self._log(f"ESP32: {line}")

    def _send_cmd(self, cmd_text):
        if not self.ser or not self.ser.is_open:
            return False
        try:
            self.ser.write((cmd_text + "\n").encode('utf-8'))
            return True
        except Exception as e:
            self._log(f"发送指令失败: {str(e)}")
            return False

    def _start_adb_flow(self):
        if not self.esp32_connected:
            self._log("错误: ESP32-C3 尚未连接！")
            return
        if not self.ble_connected:
            self._log("提示: 正在尝试触发，若无响应请确认手机已配对 ESP32-C3 ADB Master...")

        selected = self.preset_combo.get()
        preset_id = selected.split(":")[0].strip()
        pin = self.entry_pin.get().strip()

        cmd = f"RUN_FLOW {preset_id}"
        if pin:
            cmd += f" {pin}"

        self.progress_bar.set(0.05)
        self.lbl_progress_desc.configure(text="正在启动自动化开启流程...")
        self._log(f"开始执行无线 ADB 开启流程 (系统: {selected})...")
        self._send_cmd(cmd)

    def _stop_adb_flow(self):
        self._send_cmd("STOP")
        self.progress_bar.set(0)
        self.lbl_progress_desc.configure(text="已手动中止")
        self._log("已发送 STOP 中止指令。")

    def _open_settings_step(self):
        self._send_cmd("KEY GUI")
        self.after(400, lambda: self._send_cmd("TYPE settings"))
        self.after(800, lambda: self._send_cmd("KEY ENTER"))

    def _search_adb_step(self):
        self._send_cmd("KEY_COMB CTRL f")
        self.after(300, lambda: self._send_cmd("TYPE wireless"))
        self.after(700, lambda: self._send_cmd("KEY ENTER"))

    def _confirm_dialog_step(self):
        self._send_cmd("KEY RIGHT")
        self.after(200, lambda: self._send_cmd("KEY ENTER"))

    def _send_custom_text(self):
        text = self.entry_custom_text.get().strip()
        if text:
            self._send_cmd(f"TYPE {text}")
            self.entry_custom_text.delete(0, "end")

    def _auto_scan_phone_ip(self):
        self._log("正在扫描局域网可能开放 5555 端口的 ADB 设备...")
        threading.Thread(target=self._scan_ip_worker, daemon=True).start()

    def _scan_ip_worker(self):
        found_ips = []
        try:
            output = subprocess.check_output("arp -a", shell=True, text=True, errors='ignore')
            ip_candidates = re.findall(r'(\d+\.\d+\.\d+\.\d+)', output)
            valid_candidates = [ip for ip in ip_candidates if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172.")]
            valid_candidates = list(set(valid_candidates))

            for ip in valid_candidates[:30]:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.25)
                    result = s.connect_ex((ip, 5555))
                    s.close()
                    if result == 0:
                        found_ips.append(ip)
                except Exception:
                    pass

        except Exception as e:
            self.after(0, self._log, f"扫描出错: {str(e)}")

        if found_ips:
            best_ip = found_ips[0] + ":5555"
            self.after(0, lambda: self.entry_phone_ip.delete(0, "end"))
            self.after(0, lambda: self.entry_phone_ip.insert(0, best_ip))
            self.after(0, self._log, f"🎯 发现活跃 ADB 设备: {found_ips}")
        else:
            self.after(0, self._log, "未扫描到默认 5555 设备，请在手机“无线调试”页面查看显示的 IP 地址与端口并填入。")

    def _run_adb_connect(self):
        target = self.entry_phone_ip.get().strip()
        if not target:
            self._log("请先输入手机 IP 地址（如 192.168.1.100:5555）！")
            return

        self._log(f"执行: adb connect {target} ...")
        threading.Thread(target=self._adb_cmd_worker, args=(f"adb connect {target}",), daemon=True).start()

    def _run_adb_devices(self):
        self._log("执行: adb devices ...")
        threading.Thread(target=self._adb_cmd_worker, args=("adb devices -l",), daemon=True).start()

    def _open_adb_shell(self):
        target = self.entry_phone_ip.get().strip()
        cmd = "start cmd /k adb shell"
        if target:
            cmd = f"start cmd /k adb -s {target} shell"
        self._log("启动独立命令行窗口运行 ADB Shell...")
        subprocess.Popen(cmd, shell=True)

    def _launch_scrcpy(self):
        target = self.entry_phone_ip.get().strip()
        cmd = "scrcpy"
        if target:
            cmd = f"scrcpy -s {target}"
        self._log(f"尝试启动投屏: {cmd} ...")
        try:
            subprocess.Popen(cmd, shell=True)
            self._log("Scrcpy 进程已启动。")
        except Exception as e:
            self._log(f"启动 Scrcpy 失败 (请确认已将 scrcpy 加入系统 PATH 环境变量): {str(e)}")

    def _adb_cmd_worker(self, cmd):
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8)
            out = res.stdout.strip()
            err = res.stderr.strip()
            if out:
                self.after(0, self._log, f"[ADB 输出]\n{out}")
            if err:
                self.after(0, self._log, f"[ADB 错误]\n{err}")
        except subprocess.TimeoutExpired:
            self.after(0, self._log, "ADB 命令执行超时 (请检查手机与电脑是否处于同一 Wi-Fi)。")
        except FileNotFoundError:
            self.after(0, self._log, "未找到 adb 命令，请确保已安装 Android SDK Platform Tools 并加入 PATH。")
        except Exception as e:
            self.after(0, self._log, f"执行失败: {str(e)}")


if __name__ == "__main__":
    app = ADBControllerApp()
    app.mainloop()
