@echo off
chcp 65001 >nul
setlocal

REM ========================================
REM Qwen3-ASR OpenVINO GUI Launcher
REM ========================================

set "SCRIPT_DIR=%~dp0"
set "CONDA_ROOT="
set "PYTHON_EXE="

REM Find Miniconda
if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=%USERPROFILE%\miniconda3"
) else if exist "C:\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=C:\miniconda3"
) else if exist "D:\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=D:\miniconda3"
) else if exist "D:\Python\.app\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=D:\Python\.app\miniconda3"
)

if "%CONDA_ROOT%"=="" (
    echo [ERROR] Miniconda not found
    pause
    exit /b 1
)

set "CONDA_ENV=qwen_ov"
set "PYTHON_EXE=%CONDA_ROOT%\envs\%CONDA_ENV%\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating qwen_ov environment...
    call "%CONDA_ROOT%\Scripts\conda.exe" create -n %CONDA_ENV% python=3.11 -y
)

"%PYTHON_EXE%" -c "import openvino" 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    "%PYTHON_EXE%" -m pip install openvino onnxruntime librosa opencc-python-reimplemented -q
)

echo ========================================
echo Qwen3-ASR OpenVINO GUI (CPU)
echo ========================================
echo [OK] Miniconda: %CONDA_ROOT%
echo [OK] Environment: %CONDA_ENV%
echo.

echo [INFO] Starting GUI...
echo.
"%PYTHON_EXE%" "%SCRIPT_DIR%qwen3-asr-ov-gui.py"

pause
