@echo off
chcp 65001 >nul
cd /d "%~dp0"
set AUTO=
if /i "%~1"=="auto" set AUTO=1
echo === FundoLimpo - gerar instalador ===
echo.

rem 1) ambiente Python (so na primeira vez)
if not exist .venv\Scripts\python.exe (
  echo Preparando o ambiente Python pela primeira vez...
  set PY=
  where py >nul 2>nul && set PY=py -3
  if not defined PY (where python >nul 2>nul && set PY=python)
  if not defined PY (
    echo Python nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/
    echo e marque "Add python.exe to PATH". Depois rode este arquivo de novo.
    pause & exit /b 1
  )
  call :mkvenv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt pyinstaller || (echo Falha ao instalar dependencias. & pause & exit /b 1)

for /f "usebackq delims=" %%v in (`python -c "from fundolimpo.app import VERSION; print(VERSION)"`) do set VER=%%v
echo Versao: %VER%

rem 2) app empacotado (pasta dist\FundoLimpo com FundoLimpo.exe)
echo.
echo [1/2] Empacotando o app (alguns minutos)...
pyinstaller --noconfirm --clean --log-level WARN --windowed --name FundoLimpo --paths . ^
  --icon instalador\icone.ico ^
  --add-data "modelo;modelo" --add-data "camera\x64;camera\x64" --add-data "camera\x86;camera\x86" ^
  --add-data "instalador\icone.png;." ^
  --collect-binaries onnxruntime --collect-submodules onnxruntime.capi --collect-submodules pygrabber ^
  --exclude-module onnxruntime.quantization --exclude-module onnxruntime.tools --exclude-module onnxruntime.transformers ^
  --exclude-module pyvirtualcam ^
  fundolimpo\__main__.py || (echo Falha no PyInstaller. & pause & exit /b 1)

rem 3) Inno Setup (gratuito) para criar o Setup.exe
call :findiscc
if not defined ISCC (
  echo.
  echo Instalando o Inno Setup ^(gerador de instaladores, gratuito^)...
  winget install -e --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements >nul 2>nul
  call :findiscc
)
if not defined ISCC (
  echo.
  echo Nao achei o Inno Setup. Baixe e instale em https://jrsoftware.org/isdl.php
  echo e rode este arquivo de novo. ^(O app ja esta pronto em dist\FundoLimpo\FundoLimpo.exe^)
  pause & exit /b 1
)
echo.
echo [2/2] Criando o instalador...
"%ISCC%" /Q /DAppVersion=%VER% instalador\FundoLimpo.iss || (echo Falha ao criar o instalador. & pause & exit /b 1)

echo.
echo ============================================================
echo  Pronto: dist\instalador\FundoLimpo-Setup-%VER%.exe
echo  Esse arquivo unico e o que voce instala e envia pra testar.
echo ============================================================
if defined AUTO exit /b 0
explorer dist\instalador
pause
exit /b 0

:mkvenv
%PY% -m venv .venv
exit /b %errorlevel%

:findiscc
set ISCC=
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe") do (
  if exist %%p set ISCC=%%~p
)
exit /b 0
