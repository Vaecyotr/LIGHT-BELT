@echo off
chcp 65001 >nul
title 帮助信息 - Light Engine Help
cd /d %~dp0
echo.
echo ========================================
echo   灯光算法原型 - 帮助信息
echo ========================================
echo.
echo Python 版本:
.python\python.exe --version
echo.
echo 可用命令:
echo.
.python\python.exe -m light_engine --help
echo.
echo ========================================
echo 各子命令的详细帮助:
echo ========================================
echo.
echo --- demo (内置演示) ---
.python\python.exe -m light_engine demo --help
echo.
echo --- run (使用媒体文件) ---
.python\python.exe -m light_engine run --help
echo.
echo --- simulator (终端模拟器) ---
.python\python.exe -m light_engine simulator --help
echo.
echo --- export (导出数据) ---
.python\python.exe -m light_engine export --help
echo.
echo --- benchmark (性能测试) ---
.python\python.exe -m light_engine benchmark --help
echo.
pause
