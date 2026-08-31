@echo off
rem install_autostart.bat — регистрирует Монике автозапуск при входе в Windows
rem через Планировщик задач (schtasks). Запускать один раз, от имени пользователя.
rem Удалить задачу:  schtasks /delete /tn "Monica 1.0" /f
setlocal
set TASK_NAME=Monica 1.0
set STARTER=%~dp0start_monica.bat

schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel%==0 (
    echo Задача "%TASK_NAME%" уже существует — обновляю...
    schtasks /delete /tn "%TASK_NAME%" /f >nul
)
schtasks /create /tn "%TASK_NAME%" /tr "\"%STARTER%\"" /sc onlogon /rl limited /f
if %errorlevel%==0 (
    echo.
    echo OK: Моника будет запускаться при входе в Windows.
    echo    Задача: "%TASK_NAME%" ^| скрипт: %STARTER%
) else (
    echo.
    echo ОШИБКА: не удалось создать задачу. Попробуйте запустить этот файл
    echo от имени администратора или добавьте ярлык start_monica.bat в
    echo shell:startup вручную ^(Win+R ^^> shell:startup^).
)
pause
