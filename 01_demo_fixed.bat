@echo off
cd /d "%%~dp0"
"%%~dp0.python\python.exe" -m light_engine demo --duration 30 --seed 42
echo.
echo Demo finished.
pause
