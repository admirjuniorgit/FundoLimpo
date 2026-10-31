@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Rode primeiro o instalar.bat & pause & exit /b 1)
.venv\Scripts\python -c "from fundolimpo import vcam; vcam.unregister(); print('Camera removida.')"
pause
