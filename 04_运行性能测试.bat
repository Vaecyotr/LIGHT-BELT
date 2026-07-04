@echo off
chcp 65001 >nul
title 性能测试 - Benchmark
cd /d %~dp0
echo.
echo ========================================
echo   灯光算法原型 - 性能测试
echo ========================================
echo 测试 300 帧的处理速度...
echo.
.python\python.exe -m light_engine benchmark --frames 300
echo.
echo Avg FPS = 平均每秒处理帧数(越高越好)
echo P50/P95/P99 = 帧处理耗时(毫秒,越低越好)
echo 30 FPS 以上即可满足实时灯光控制
echo 当前测试环境: Windows x86-64 (非RK3588)
pause
