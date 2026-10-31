@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === FundoLimpo - instalacao ===
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo.
  echo Python nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/
  echo e marque "Add python.exe to PATH" na instalacao. Depois rode este arquivo de novo.
  pause & exit /b 1
)
if not exist .venv (
  echo Criando ambiente...
  %PY% -m venv .venv || (echo Falha ao criar o ambiente. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
echo Instalando dependencias (pode levar alguns minutos)...
python -m pip install -r requirements.txt || (echo Falha na instalacao. & pause & exit /b 1)
echo.
echo Instalando a camera virtual "FundoLimpo Camera" (o Windows vai pedir permissao)...
python -c "from fundolimpo import vcam; import sys; ok=vcam.register(); print('Camera instalada!' if ok else 'Nao instalou - da pra instalar depois pelo botao no app.')"
echo.
echo Pronto! Agora abra o "abrir.bat".
pause
