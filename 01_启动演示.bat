@echo off
chcp 65001 >nul
title 灯光演示 - Light Engine Demo
cd /d "%~dp0"

echo.
echo ========================================
echo   灯光算法原型 - 内置演示
echo ========================================
echo.
echo 正在使用内置合成数据运行灯光演示...
echo 运行时间: 30秒 (按 Ctrl+C 可随时停止)
echo.

".python\python.exe" -m light_engine demo --duration 30 --seed 42

echo.
echo 演示结束。
pause