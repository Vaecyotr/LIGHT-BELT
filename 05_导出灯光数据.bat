@echo off
chcp 65001 >nul
title 导出灯光数据 - JSON Export
cd /d %~dp0
echo.
echo ========================================
echo   灯光算法原型 - 导出灯光数据
echo ========================================
echo 正在导出 60 帧灯光数据到 output\ 目录...
if not exist "output" mkdir "output"
.python\python.exe -m light_engine export --output output\exported_lights.jsonl --max-frames 60
echo.
echo 导出完成! 文件: output\exported_lights.jsonl
echo 这是文本文件，每行一个JSON对象，记录了一帧所有灯带和区域的颜色。
pause
