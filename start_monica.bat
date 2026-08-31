@echo off
rem start_monica.bat — запуск сервера Моники (Фаза 8-prep).
rem Убивает висящий процесс на порту 8900 и стартует сервер в этом окне.
cd /d "%~dp0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8900 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
echo Monica 1.0 starting...
python app\server.py
pause
