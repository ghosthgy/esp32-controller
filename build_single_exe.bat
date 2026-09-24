@echo off
chcp 65001 >nul
echo ===================================================
echo   ESP32-C3 手机网络ADB控制器 - 单文件 EXE 打包
echo ===================================================

echo 正在打包单文件 EXE (此过程约需 20-40 秒)...
pyinstaller --noconfirm --onefile --windowed --name "ESP32_ADB_Controller_Single" --collect-all customtkinter esp32_adb_controller.py

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo   [成功] 单文件版 EXE 构建完成！
    echo   文件路径: dist\ESP32_ADB_Controller_Single.exe
    echo ===================================================
) else (
    echo [错误] 打包失败。
)

pause
