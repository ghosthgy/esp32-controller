@echo off
chcp 65001 >nul
echo ===================================================
echo   ESP32-C3 手机网络ADB控制器 - EXE 打包构建程序
echo ===================================================

echo [1/3] 正在检查 Python 与依赖环境...
python -c "import customtkinter, serial; print('依赖环境完整')"
if %errorlevel% neq 0 (
    echo [错误] 缺少必要依赖，正在安装...
    python -m pip install customtkinter pyserial pyinstaller
)

echo.
echo [2/3] 正在通过 PyInstaller 打包生成独立 EXE 文件...
pyinstaller --noconfirm --onedir --windowed --name "ESP32_ADB_Controller" --collect-all customtkinter esp32_adb_controller.py

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo   [成功] EXE 构建完成！
    echo   可执行文件位于: dist\ESP32_ADB_Controller\ESP32_ADB_Controller.exe
    echo ===================================================
) else (
    echo [错误] 打包失败，请检查上方日志。
)

pause
