@echo off
chcp 65001 >nul
title 运行测试 - Light Engine Tests
cd /d %~dp0
echo.
echo ========================================
echo   灯光算法原型 - 自动化测试
echo ========================================
echo.
echo 运行所有测试...
echo.
.python\python.exe -m pytest tests/ -v
echo.
echo ========================================
echo 测试完成。上方显示的是测试结果。
echo 绿色 PASSED = 通过
echo 红色 FAILED = 失败(需要检查代码)
echo 如果全部绿色，说明核心算法正确。
echo ========================================
pause
