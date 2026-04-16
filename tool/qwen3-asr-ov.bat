@echo off
chcp 65001 >nul
setlocal

REM ========================================
REM Qwen3-ASR OpenVINO CLI Launcher
REM 自動建立/使用 qwen_ov conda 環境
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
    echo Please install from: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

set "CONDA_BAT=%CONDA_ROOT%\Scripts\conda.exe"

REM Check if qwen_ov environment exists
if exist "%CONDA_ROOT%\envs\qwen_ov\python.exe" (
    echo [OK] Found qwen_ov environment
    set "PYTHON_EXE=%CONDA_ROOT%\envs\qwen_ov\python.exe"
) else (
    echo [INFO] qwen_ov environment not found, creating...
    "%CONDA_BAT%" create -n qwen_ov python=3.11 -y
    if errorlevel 1 (
        echo [ERROR] Failed to create environment
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%CONDA_ROOT%\envs\qwen_ov\python.exe"

    echo [INFO] Installing packages...
    "%PYTHON_EXE%" -m pip install openvino>=2024.0.0 onnxruntime>=1.17.0 librosa>=0.10.0 opencc-python-reimplemented>=0.1.7 soundfile>=0.12.0 numpy>=1.24.0 -q

    echo [INFO] Packages installed
)

REM Show Python version
"%PYTHON_EXE%" -c "import sys; print('[OK] Python:', sys.version.split()[0])"

REM Check OpenVINO
"%PYTHON_EXE%" -c "import openvino; print('[OK] OpenVINO:', openvino.__version__)" 2>nul || (
    echo [WARN] OpenVINO not found, installing...
    "%PYTHON_EXE%" -m pip install openvino>=2024.0.0 -q
)

REM Launch CLI
cd /d "%SCRIPT_DIR%"
echo.
echo Running: qwen3-asr-ov.py %*
echo.
"%PYTHON_EXE%" qwen3-asr-ov.py %*

pause
