@echo off
chcp 65001 >nul
title 灯光模拟器 - Terminal Simulator
cd /d %~dp0
echo.
echo ========================================
echo   灯光算法原型 - 终端模拟器
echo ========================================
echo.
echo 模拟器将在终端中显示:
echo   - 6条灯带的逐颗像素颜色
echo   - 6个RGBW区域的整体颜色
echo   - 当前FPS、灯效模式、音频/视频信息
echo.
echo 按键盘 Q 键退出
echo.
.python\python.exe -m light_engine simulator --duration 60 --seed 42
echo.
echo 模拟器已退出。
pause
